"""
Unit tests for `baseapp_core.graphql.utils.resolve_document_content_object`.

The helper is used by `baseapp_follows` and `baseapp_comments` to resolve
`DocumentId.content_object` through a request-scoped cache. Tests use plain
`SimpleNamespace` stand-ins for `DocumentId` and the GraphQL `info` so the helper
can be exercised without spinning up a Django test database — same approach the
optimizer's other unit tests in this directory use (see
`test_graphql_object_type_pre_optimization.py`).
"""

from types import SimpleNamespace

import factory

from baseapp_core.graphql.utils import resolve_document_content_object


class _DocumentRowFactory(factory.Factory):
    class Meta:
        model = SimpleNamespace

    content_type_id = 10
    object_id = factory.Sequence(lambda n: n + 1)
    content_object = None


def _make_info(context=None) -> SimpleNamespace:
    if context is None:
        context = SimpleNamespace()
    return SimpleNamespace(context=context)


def test_returns_none_when_document_is_none() -> None:
    info = _make_info()
    assert resolve_document_content_object(None, info) is None


def test_resolves_via_content_object_descriptor_on_first_call() -> None:
    profile = object()
    document = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=profile)
    info = _make_info()

    result = resolve_document_content_object(document, info)

    assert result is profile


def test_caches_resolution_on_info_context() -> None:
    profile = object()
    document = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=profile)
    info = _make_info()

    resolve_document_content_object(document, info)

    cache = info.context._document_content_object_cache
    assert cache == {(10, 1): profile}


def test_returns_cached_value_without_touching_descriptor_again() -> None:
    """
    A second call for the same `(content_type_id, object_id)` must not re-read
    `document.content_object` — that's the whole point of the cache.
    """
    cached_profile = object()
    other_profile = object()

    # First document populates the cache via `content_object`.
    first_doc = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=cached_profile)
    info = _make_info()
    resolve_document_content_object(first_doc, info)

    # Second document has the same cache key but a different `content_object` —
    # if the helper hits the descriptor, we'd see `other_profile`. We expect the
    # cached value instead.
    second_doc = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=other_profile)
    result = resolve_document_content_object(second_doc, info)

    assert result is cached_profile


def test_distinct_cache_keys_each_get_their_own_entry() -> None:
    a = object()
    b = object()
    doc_a = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=a)
    doc_b = _DocumentRowFactory(content_type_id=10, object_id=2, content_object=b)
    info = _make_info()

    assert resolve_document_content_object(doc_a, info) is a
    assert resolve_document_content_object(doc_b, info) is b
    assert info.context._document_content_object_cache == {(10, 1): a, (10, 2): b}


def test_different_content_types_with_same_object_id_do_not_collide() -> None:
    profile = object()
    page = object()
    doc_profile = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=profile)
    doc_page = _DocumentRowFactory(content_type_id=20, object_id=1, content_object=page)
    info = _make_info()

    assert resolve_document_content_object(doc_profile, info) is profile
    assert resolve_document_content_object(doc_page, info) is page


def test_custom_cache_attr_writes_to_separate_namespace() -> None:
    profile = object()
    document = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=profile)
    info = _make_info()

    resolve_document_content_object(document, info, cache_attr="_comment_target_cache")

    assert info.context._comment_target_cache == {(10, 1): profile}
    # Default attribute must remain untouched so two callers can keep separate caches.
    assert not hasattr(info.context, "_document_content_object_cache")


def test_caches_none_result_so_a_missing_target_is_not_re_queried() -> None:
    """
    A deleted target with a stale `DocumentId` resolves to `None`. The helper
    must remember that `None` so subsequent calls don't keep hitting the DB
    descriptor for the same missing object.
    """
    doc_first = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=None)
    info = _make_info()

    assert resolve_document_content_object(doc_first, info) is None

    sentinel = object()
    doc_second = _DocumentRowFactory(content_type_id=10, object_id=1, content_object=sentinel)
    assert resolve_document_content_object(doc_second, info) is None
