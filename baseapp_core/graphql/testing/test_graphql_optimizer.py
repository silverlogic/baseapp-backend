from unittest.mock import MagicMock

import pytest
from graphql.language.ast import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    NameNode,
    SelectionSetNode,
)
from graphql.pyutils import Path
from query_optimizer.compiler import OptimizationCompiler
from query_optimizer.filter_info import FilterInfoCompiler
from query_optimizer.typing import GQLInfo

from baseapp_core.graphql.optimizer import (
    ConnectionFieldNodeExtractor,
    FilterInfoCompilerPatch,
    GraphQLASTWalkerPatchMixin,
    OptimizationCompilerPatch,
    ResolveInfoProxy,
)


class TestResolveInfoProxy:
    @pytest.fixture
    def mock_info(self):
        info = MagicMock(spec=GQLInfo)
        info.schema.query_type = MagicMock()
        info.parent_type = MagicMock()
        info.field_nodes = [MagicMock()]
        return info

    @pytest.fixture
    def mock_field_nodes(self):
        field_node = MagicMock(spec=FieldNode)
        return [field_node]

    def test_init_without_field_nodes(self, mock_info):
        proxy = ResolveInfoProxy(mock_info)

        assert proxy._info == mock_info
        assert proxy._parent_type == mock_info.schema.query_type
        assert proxy._queryset_field_nodes is None
        assert proxy._connection_field_nodes is None
        assert proxy._use_mode == "queryset"

    def test_init_with_queryset_field_nodes(self, mock_info, mock_field_nodes):
        proxy = ResolveInfoProxy(mock_info, queryset_field_nodes=mock_field_nodes)

        assert proxy._info == mock_info
        assert proxy._parent_type == mock_info.schema.query_type
        assert proxy._queryset_field_nodes == mock_field_nodes
        assert proxy._connection_field_nodes is None

    def test_init_with_connection_field_nodes(self, mock_info, mock_field_nodes):
        proxy = ResolveInfoProxy(mock_info, connection_field_nodes=mock_field_nodes)

        assert proxy._info == mock_info
        assert proxy._parent_type == mock_info.schema.query_type
        assert proxy._queryset_field_nodes is None
        assert proxy._connection_field_nodes == mock_field_nodes

    def test_parent_type_property(self, mock_info):
        proxy = ResolveInfoProxy(mock_info)
        assert proxy.parent_type == mock_info.schema.query_type

    def test_original_parent_type_property(self, mock_info):
        proxy = ResolveInfoProxy(mock_info)
        assert proxy.original_parent_type == mock_info.parent_type

    def test_field_nodes_property_without_custom_nodes(self, mock_info):
        proxy = ResolveInfoProxy(mock_info)
        assert proxy.field_nodes == mock_info.field_nodes

    def test_field_nodes_property_with_queryset_nodes(self, mock_info, mock_field_nodes):
        proxy = ResolveInfoProxy(mock_info, queryset_field_nodes=mock_field_nodes)
        assert proxy.field_nodes == mock_field_nodes

    def test_field_nodes_property_with_connection_nodes(self, mock_info, mock_field_nodes):
        proxy = ResolveInfoProxy(
            mock_info, connection_field_nodes=mock_field_nodes, use_mode="filter_info"
        )
        assert proxy.field_nodes == mock_field_nodes

    def test_get_info_proxy(self, mock_info, mock_field_nodes):
        queryset_nodes = [MagicMock(spec=FieldNode)]
        connection_nodes = [MagicMock(spec=FieldNode)]
        proxy = ResolveInfoProxy(
            mock_info,
            queryset_field_nodes=queryset_nodes,
            connection_field_nodes=connection_nodes,
            use_mode="queryset",
        )

        filter_proxy = proxy.get_info_proxy("filter_info")
        assert filter_proxy._use_mode == "filter_info"
        assert filter_proxy._queryset_field_nodes == queryset_nodes
        assert filter_proxy._connection_field_nodes == connection_nodes
        assert filter_proxy.field_nodes == connection_nodes

        queryset_proxy = proxy.get_info_proxy("queryset")
        assert queryset_proxy._use_mode == "queryset"
        assert queryset_proxy.field_nodes == queryset_nodes

    def test_getattr_delegates_to_info(self, mock_info):
        mock_info.some_attribute = "test_value"
        proxy = ResolveInfoProxy(mock_info)

        assert proxy.some_attribute == "test_value"


class TestGraphQLASTWalkerPatchMixin:
    @pytest.fixture
    def mock_info(self):
        info = MagicMock(spec=GQLInfo)
        info.parent_type = MagicMock()
        info.field_nodes = [MagicMock()]
        return info

    @pytest.fixture
    def mock_proxy_info(self, mock_info):
        return ResolveInfoProxy(mock_info)

    @pytest.fixture
    def walker_with_regular_info(self, mock_info):
        walker = MagicMock()
        walker.info = mock_info
        walker.handle_selections = MagicMock(return_value="result")
        return type(
            "TestWalker",
            (GraphQLASTWalkerPatchMixin,),
            {
                "info": mock_info,
                "handle_selections": MagicMock(return_value="result"),
            },
        )()

    @pytest.fixture
    def walker_with_proxy_info(self, mock_proxy_info):
        return type(
            "TestWalker",
            (GraphQLASTWalkerPatchMixin,),
            {
                "info": mock_proxy_info,
                "handle_selections": MagicMock(return_value="result"),
            },
        )()

    def test_run_with_regular_info(self, walker_with_regular_info, mock_info):
        result = walker_with_regular_info.run()

        assert result == "result"
        walker_with_regular_info.handle_selections.assert_called_once_with(
            mock_info.parent_type, mock_info.field_nodes
        )

    def test_run_with_proxy_info(self, walker_with_proxy_info, mock_proxy_info):
        result = walker_with_proxy_info.run()

        assert result == "result"
        walker_with_proxy_info.handle_selections.assert_called_once_with(
            mock_proxy_info.original_parent_type, mock_proxy_info.field_nodes
        )


class TestOptimizationCompilerPatch:
    @pytest.fixture
    def mock_info(self):
        info = MagicMock(spec=GQLInfo)
        info.schema.query_type = MagicMock()
        info.parent_type = MagicMock()
        info.field_nodes = [MagicMock()]
        return info

    def test_inherits_from_mixin_and_compiler(self):
        assert issubclass(OptimizationCompilerPatch, GraphQLASTWalkerPatchMixin)
        assert issubclass(OptimizationCompilerPatch, OptimizationCompiler)

    def test_run_with_proxy_switches_to_queryset_mode(self, mock_info):
        queryset_nodes = [MagicMock(spec=FieldNode)]
        proxy = ResolveInfoProxy(
            mock_info, queryset_field_nodes=queryset_nodes, use_mode="filter_info"
        )
        compiler = OptimizationCompilerPatch(proxy, max_complexity=None)
        compiler.info = proxy
        compiler.handle_selections = MagicMock(return_value="result")

        result = compiler.run()

        assert result == "result"
        assert compiler.info._use_mode == "queryset"
        compiler.handle_selections.assert_called_once()


class TestFilterInfoCompilerPatch:
    @pytest.fixture
    def mock_info(self):
        info = MagicMock(spec=GQLInfo)
        info.schema.query_type = MagicMock()
        info.parent_type = MagicMock()
        info.field_nodes = [MagicMock()]
        return info

    def test_inherits_from_mixin_and_compiler(self):
        assert issubclass(FilterInfoCompilerPatch, GraphQLASTWalkerPatchMixin)
        assert issubclass(FilterInfoCompilerPatch, FilterInfoCompiler)

    def test_run_with_proxy_switches_to_filter_info_mode(self, mock_info):
        connection_nodes = [MagicMock(spec=FieldNode)]
        proxy = ResolveInfoProxy(
            mock_info, connection_field_nodes=connection_nodes, use_mode="queryset"
        )
        compiler = FilterInfoCompilerPatch(proxy)
        compiler.info = proxy
        compiler.handle_selections = MagicMock(return_value="result")

        result = compiler.run()

        assert result == "result"
        assert compiler.info._use_mode == "filter_info"
        compiler.handle_selections.assert_called_once()


class TestConnectionFieldNodeExtractor:
    def _create_name_node(self, value: str) -> NameNode:
        return NameNode(value=value)

    def _create_field_node(
        self, name: str, alias: str | None = None, selection_set: SelectionSetNode | None = None
    ) -> FieldNode:
        name_node = self._create_name_node(name)
        alias_node = self._create_name_node(alias) if alias else None
        return FieldNode(
            name=name_node,
            alias=alias_node,
            selection_set=selection_set,
        )

    def _create_selection_set(self, selections: list) -> SelectionSetNode:
        return SelectionSetNode(selections=selections)

    def _create_path(self, keys: list[str]) -> Path | None:
        path = None
        for key in keys:
            path = Path(prev=path, key=key, typename=None)
        return path

    @pytest.fixture
    def mock_info_basic(self):
        info = MagicMock(spec=GQLInfo)
        info.fragments = {}
        return info

    def test_path_to_field_names_single_key(self, mock_info_basic):
        path = self._create_path(["comments"])
        # Create extractor with minimal required fields to test the method directly
        extractor = ConnectionFieldNodeExtractor.__new__(ConnectionFieldNodeExtractor)
        extractor._info = mock_info_basic
        result = extractor._path_to_field_names(path)

        assert result == ["comments"]

    def test_path_to_field_names_multiple_keys(self, mock_info_basic):
        path = self._create_path(["node", "comments"])
        # Create extractor with minimal required fields to test the method directly
        extractor = ConnectionFieldNodeExtractor.__new__(ConnectionFieldNodeExtractor)
        extractor._info = mock_info_basic
        result = extractor._path_to_field_names(path)

        assert result == ["node", "comments"]

    def test_path_to_field_names_none(self, mock_info_basic):
        # Create extractor with minimal required fields to test the method directly
        extractor = ConnectionFieldNodeExtractor.__new__(ConnectionFieldNodeExtractor)
        extractor._info = mock_info_basic
        result = extractor._path_to_field_names(None)

        assert result == []

    def test_response_name_without_alias(self, mock_info_basic):
        field = self._create_field_node("comments")
        # Create extractor with minimal required fields to test the method directly
        extractor = ConnectionFieldNodeExtractor.__new__(ConnectionFieldNodeExtractor)
        extractor._info = mock_info_basic

        assert extractor._response_name(field) == "comments"

    def test_response_name_with_alias(self, mock_info_basic):
        field = self._create_field_node("comments", alias="myComments")
        # Create extractor with minimal required fields to test the method directly
        extractor = ConnectionFieldNodeExtractor.__new__(ConnectionFieldNodeExtractor)
        extractor._info = mock_info_basic

        assert extractor._response_name(field) == "myComments"

    def test_iter_matching_fields_finds_field_node(self, mock_info_basic):
        field1 = self._create_field_node("edges")
        field2 = self._create_field_node("other")
        selections = [field1, field2]
        # Create extractor with minimal required fields to test the method directly
        extractor = ConnectionFieldNodeExtractor.__new__(ConnectionFieldNodeExtractor)
        extractor._info = mock_info_basic

        results = list(extractor._iter_matching_fields(selections, "edges"))
        assert len(results) == 1
        assert results[0] == field1

    def test_iter_matching_fields_with_inline_fragment(self, mock_info_basic):
        inner_field = self._create_field_node("edges")
        selection_set = self._create_selection_set([inner_field])
        inline_fragment = InlineFragmentNode(selection_set=selection_set)
        selections = [inline_fragment]
        # Create extractor with minimal required fields to test the method directly
        extractor = ConnectionFieldNodeExtractor.__new__(ConnectionFieldNodeExtractor)
        extractor._info = mock_info_basic

        results = list(extractor._iter_matching_fields(selections, "edges"))
        assert len(results) == 1
        assert results[0] == inner_field

    def test_iter_matching_fields_with_fragment_spread(self, mock_info_basic):
        inner_field = self._create_field_node("edges")
        selection_set = self._create_selection_set([inner_field])
        fragment_def = FragmentDefinitionNode(
            name=self._create_name_node("TestFragment"),
            type_condition=MagicMock(),
            selection_set=selection_set,
        )
        mock_info_basic.fragments = {"TestFragment": fragment_def}

        fragment_spread = FragmentSpreadNode(name=self._create_name_node("TestFragment"))
        selections = [fragment_spread]
        # Create extractor with minimal required fields to test the method directly
        extractor = ConnectionFieldNodeExtractor.__new__(ConnectionFieldNodeExtractor)
        extractor._info = mock_info_basic

        results = list(extractor._iter_matching_fields(selections, "edges"))
        assert len(results) == 1
        assert results[0] == inner_field

    def test_extract_connection_resolver_root_field_simple(self, mock_info_basic):
        # Create AST structure: comments { edges { node { comments { id } } } }
        inner_comments = self._create_field_node("comments")
        inner_selection_set = self._create_selection_set([inner_comments])
        node_field = self._create_field_node("node", selection_set=inner_selection_set)
        node_selection_set = self._create_selection_set([node_field])
        edges_field = self._create_field_node("edges", selection_set=node_selection_set)
        edges_selection_set = self._create_selection_set([edges_field])
        outer_comments = self._create_field_node("comments", selection_set=edges_selection_set)

        mock_info_basic.field_nodes = [outer_comments]
        mock_info_basic.path = self._create_path(["comments"])

        extractor = ConnectionFieldNodeExtractor(mock_info_basic)
        result = extractor.get_sliced_field_nodes()

        assert len(result) == 1
        assert result[0] == inner_comments

    def test_extract_connection_resolver_root_field_with_alias(self, mock_info_basic):
        # Create AST: myComments: comments { edges { node { myComments { id } } } }
        # The inner field should also have the alias to match the path
        inner_comments = self._create_field_node("comments", alias="myComments")
        inner_selection_set = self._create_selection_set([inner_comments])
        node_field = self._create_field_node("node", selection_set=inner_selection_set)
        node_selection_set = self._create_selection_set([node_field])
        edges_field = self._create_field_node("edges", selection_set=node_selection_set)
        edges_selection_set = self._create_selection_set([edges_field])
        outer_comments = self._create_field_node(
            "comments", alias="myComments", selection_set=edges_selection_set
        )

        mock_info_basic.field_nodes = [outer_comments]
        mock_info_basic.path = self._create_path(["myComments"])

        extractor = ConnectionFieldNodeExtractor(mock_info_basic)
        result = extractor.get_sliced_field_nodes()

        assert len(result) == 1
        assert result[0] == inner_comments

    def test_extract_connection_resolver_root_field_no_selection_set(self, mock_info_basic):
        outer_comments = self._create_field_node("comments", selection_set=None)
        mock_info_basic.field_nodes = [outer_comments]
        mock_info_basic.path = self._create_path(["comments"])

        extractor = ConnectionFieldNodeExtractor(mock_info_basic)
        result = extractor.get_sliced_field_nodes()

        assert result == []

    def test_extract_connection_resolver_root_field_no_edges(self, mock_info_basic):
        other_field = self._create_field_node("other")
        selection_set = self._create_selection_set([other_field])
        outer_comments = self._create_field_node("comments", selection_set=selection_set)

        mock_info_basic.field_nodes = [outer_comments]
        mock_info_basic.path = self._create_path(["comments"])

        extractor = ConnectionFieldNodeExtractor(mock_info_basic)
        result = extractor.get_sliced_field_nodes()

        assert result == []

    def test_extract_connection_resolver_root_field_multiple_matches(self, mock_info_basic):
        # Create structure with two matching inner comments fields
        inner_comments1 = self._create_field_node("comments")
        inner_comments2 = self._create_field_node("comments")
        inner_selection_set = self._create_selection_set([inner_comments1, inner_comments2])
        node_field = self._create_field_node("node", selection_set=inner_selection_set)
        node_selection_set = self._create_selection_set([node_field])
        edges_field = self._create_field_node("edges", selection_set=node_selection_set)
        edges_selection_set = self._create_selection_set([edges_field])
        outer_comments = self._create_field_node("comments", selection_set=edges_selection_set)

        mock_info_basic.field_nodes = [outer_comments]
        mock_info_basic.path = self._create_path(["comments"])

        extractor = ConnectionFieldNodeExtractor(mock_info_basic)
        result = extractor.get_sliced_field_nodes()

        assert len(result) == 2
        assert inner_comments1 in result
        assert inner_comments2 in result
