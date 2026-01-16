from typing import Any, Literal, Optional

from django.db.models import QuerySet
from graphql.language.ast import (
    FieldNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    SelectionNode,
)
from graphql.pyutils import Path
from query_optimizer.compiler import OptimizationCompiler
from query_optimizer.filter_info import FilterInfoCompiler
from query_optimizer.typing import GQLInfo
from query_optimizer.utils import mark_optimized


class ResolveInfoProxy:
    """
    Proxy for GraphQL resolve info to enable optimization of nested querysets.

    The optimizer was designed to work only with querysets loaded from the root
    GraphQL query. This proxy allows optimizing other querysets by making them
    appear as if they were part of the root query.

    The proxy overrides `parent_type` and allows custom `field_nodes` to be
    provided. The original AST walker uses `info.parent_type` to recursively
    traverse the AST, which only works from the root query. By artificially
    setting `parent_type` to the root query type, we can traverse the AST
    from any level. Pass the `field_nodes` that correspond to the query you
    want to optimize.
    """

    __slots__ = (
        "_info",
        "_parent_type",
        "_queryset_field_nodes",
        "_connection_field_nodes",
        "_use_mode",
    )

    def __init__(
        self,
        info: GQLInfo,
        queryset_field_nodes: Optional[list[FieldNode]] = None,
        connection_field_nodes: Optional[list[FieldNode]] = None,
        use_mode: Literal["queryset", "filter_info"] = "queryset",
    ) -> None:
        """
        Initialize the proxy.

        Args:
            info: The original GraphQL resolve info object.
            queryset_field_nodes: Optional list of field nodes to use in the optimizer compilation.
            connection_field_nodes: Optional list of field nodes to use in the filter info compiler.
        """
        self._info = info
        self._parent_type = info.schema.query_type
        self._queryset_field_nodes = queryset_field_nodes
        self._connection_field_nodes = connection_field_nodes
        self._use_mode = use_mode

    def get_info_proxy(
        self, use_mode: Literal["queryset", "filter_info"] = "queryset"
    ) -> "ResolveInfoProxy":
        queryset_nodes = getattr(self, "_queryset_field_nodes", None)
        connection_nodes = getattr(self, "_connection_field_nodes", None)
        new_proxy = ResolveInfoProxy(
            self._info,
            queryset_field_nodes=queryset_nodes,
            connection_field_nodes=connection_nodes,
            use_mode=use_mode,
        )
        return new_proxy

    @property
    def parent_type(self) -> Any:
        return self._parent_type

    @property
    def original_parent_type(self) -> Any:
        return self._info.parent_type

    @property
    def field_nodes(self) -> list[FieldNode]:
        return (
            self._queryset_field_nodes
            if self._use_mode == "queryset"
            else self._connection_field_nodes
        ) or self._info.field_nodes

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying info object."""
        return getattr(self._info, name)


class GraphQLASTWalkerPatchMixin:
    """
    Mixin that patches GraphQLASTWalker to support ResolveInfoProxy.

    Modifies the `run` method to use the `parent_type` defined in the
    ResolveInfoProxy object, enabling AST traversal from non-root query
    levels.
    """

    def run(self) -> Any:
        selections = self.info.field_nodes
        if isinstance(self.info, ResolveInfoProxy):
            field_type = self.info.original_parent_type
        else:
            field_type = self.info.parent_type
        return self.handle_selections(field_type, selections)


class OptimizationCompilerPatch(GraphQLASTWalkerPatchMixin, OptimizationCompiler):
    """
    Patched optimization compiler with ResolveInfoProxy support.

    The original OptimizationCompiler class uses swappable_by_subclassing,
    which will be automatically overridden by this class when loaded at
    runtime. This enables optimization of querysets from connection
    resolvers.
    """

    def run(self) -> Any:
        if isinstance(self.info, ResolveInfoProxy):
            self.info = self.info.get_info_proxy("queryset")
        return super().run()


class FilterInfoCompilerPatch(GraphQLASTWalkerPatchMixin, FilterInfoCompiler):
    """
    Patched filter info compiler with ResolveInfoProxy support.

    The original FilterInfoCompiler class uses swappable_by_subclassing,
    which will be automatically overridden by this class when loaded at
    runtime. This enables filter optimization from connection resolvers.
    """

    def run(self) -> Any:
        if isinstance(self.info, ResolveInfoProxy):
            self.info = self.info.get_info_proxy("filter_info")
        return super().run()


class ConnectionFieldNodeExtractor:
    """
    Extracts field nodes for nested queries where the root is the same object type as the list.

    This class handles the special case of nested connection queries where a connection field
    (e.g., `comments`) is queried on objects of the same type that are being resolved. When
    GraphQL resolves a connection field, `info.field_nodes` refers to the outer connection
    field, but the queryset represents objects accessed under `edges -> node`.

    Example nested query (comments -> comments):
        node {
          comments {
            edges {
              node {
                id
                comments {  # <-- nested query, same object type (Comment -> Comment)
                  id
                }
              }
            }
          }
        }

    When resolving the OUTER `comments` connection:
        - `info.field_nodes` refers to: `comments { edges { node { ... } } }`
        - The queryset represents Comment objects at: `edges -> node`
        - To optimize the nested `comments` queryset, we need field nodes from: `edges -> node -> comments`

    This class extracts the nested field nodes under `edges.node` that match the connection
    field's response name, enabling proper query optimization for nested queries of the same
    object type from within connection resolvers.
    """

    def __init__(self, info: GQLInfo):
        self._info = info

    def _path_to_field_names(self, path: Path | None) -> list[str]:
        names = []
        while path:
            if isinstance(path.key, str):
                names.append(path.key)
            path = path.prev
        return list(reversed(names))

    def _iter_matching_fields(self, selections: list[SelectionNode], name: str) -> list[FieldNode]:
        """Iterate through selections to find fields matching the given name."""
        for sel in selections:
            if isinstance(sel, FieldNode) and sel.name.value == name:
                yield sel

            elif isinstance(sel, InlineFragmentNode):
                yield from self._iter_matching_fields(sel.selection_set.selections, name)

            elif isinstance(sel, FragmentSpreadNode):
                frag = self._info.fragments[sel.name.value]
                yield from self._iter_matching_fields(frag.selection_set.selections, name)

    def _response_name(self, field: FieldNode) -> str:
        """Get the response name from a field (alias if present, otherwise name)."""
        return field.alias.value if field.alias else field.name.value

    def _extract_connection_resolver_root_field(self) -> list[FieldNode]:
        """
        Extract FieldNode(s) under edges->node that match the connection field's response name.

        For nested queries where the root is the same object type as the list (e.g., comments -> comments),
        this returns the FieldNode(s) under `edges->node` that correspond to the same response name
        as the connection field. This enables proper optimization of nested querysets from within
        connection resolvers.

        If no matching field is found, returns all FieldNodes within the node as fallback.
        """
        wanted = self._path_to_field_names(self._info.path)[-1]  # e.g. "comments" or alias

        out = []
        fallback_nodes = []

        for conn in self._info.field_nodes:
            if not conn.selection_set:
                continue

            for edges in self._iter_matching_fields(conn.selection_set.selections, "edges"):
                if not edges.selection_set:
                    continue

                for node in self._iter_matching_fields(edges.selection_set.selections, "node"):
                    if not node.selection_set:
                        continue

                    node_field_nodes = []
                    for sel in node.selection_set.selections:
                        if isinstance(sel, FieldNode):
                            node_field_nodes.append(sel)
                            if self._response_name(sel) == wanted:
                                out.append(sel)

                    if not out and node_field_nodes:
                        fallback_nodes.extend(node_field_nodes)

        return out if out else fallback_nodes

    def get_sliced_field_nodes(self) -> list[FieldNode]:
        field_nodes = self._extract_connection_resolver_root_field()
        return field_nodes


def skip_ast_walker(qs: QuerySet) -> QuerySet:
    """
    Since comments can be nested (optimization doesn't work properly when comments -> comments),
    we need to mark the .node() as optimized so the system skips the AST walker.
    """
    mark_optimized(qs)
    return qs
