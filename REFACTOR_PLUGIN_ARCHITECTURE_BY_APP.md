# Plugin Architecture Refactor by App

This document lists **refactor points per app** to align with the [plugin architecture](baseapp_core/plugins/README.md). Use it as a checklist when rebasing or migrating each package.

**Subsections used for each app:**
- **Database Migration**
  - Keep concrete models that should **not** be extended.
  - Remove concrete models that **can and should** be extendable (leave only abstract/swappable; the project or another app defines the concrete model).
  - If **all** concrete models in an app are removed, **delete that app’s migrations folder**.
- **Database Coupling**
  - Remove **all** model coupling between baseapp apps.
  - Coupling includes: direct FKs or relations to another app’s model (e.g. via swapper), mixins from other apps (e.g. **CommentableModel**, BlockableModel, FollowableModel, ReportableModel, PageMixin, ProfilableModel), and any import of another app’s models for use in fields or inheritance.
  - **DocumentId** is the decoupling mechanism (central identity); **CommentableModel** is one form of coupling (to the comments app) and must be removed, but it is not the only form.
  - If an app has no such coupling, state that; if it has coupling, describe it and state that it must be removed.
- **Settings**
  - Plugin registry: `INSTALLED_APPS`, `MIDDLEWARE`, `AUTHENTICATION_BACKENDS`, `GRAPHENE__MIDDLEWARE`, extra settings, Constance.
  - Contribution via `plugin.py` and consumption via `plugin_registry.get(...)`.
- **URLs**
  - Contribute `urlpatterns` / `v1_urlpatterns` via `plugin.py` callbacks.
  - Project uses `plugin_registry.get_all_urlpatterns()` / `get_all_v1_urlpatterns()`.
- **GraphQL shared interfaces**
  - Register interfaces by name in `AppConfig.ready()`.
  - Consumers opt in via `graphql_shared_interface_registry.get_interfaces([...], default_interfaces)` (no cross-package interface imports).
- **Shared services**
  - Register services in `AppConfig.ready()`; consumers use `shared_service_registry.get_service(name)`.
  - If another app imports or calls this app’s code (serializers, helpers, `send_notification`, URLPath logic, etc.), expose that as a shared service and have consumers use `get_service(name)` instead.

**Additional areas** (called out where relevant): **Imports** (remove cross-package runtime imports), **Entry points** (plugin in root `setup.cfg`), **Signals** (e.g. `document_created` in `ready()`), **Swapper** (model pointers), **GraphQL schema** (contributing queries/mutations/subscriptions via `plugin.py`).

---

## baseapp_auth

- **Database Migration**
  - Keep concrete models that should not be extended; remove any that can and should be extendable.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Coupling to remove:** User (or abstract user) depends on **baseapp_profiles**: uses `ProfilableModel` and FK to Profile via swapper.
  - Remove this coupling (e.g. project wires User–Profile, or use a neutral identity such as DocumentId where appropriate).
- **Settings**
  - Add to plugin `get_settings()`: `INSTALLED_APPS`, `MIDDLEWARE`, `AUTHENTICATION_BACKENDS`, `GRAPHENE__MIDDLEWARE` if auth contributes any; plus `graphql_queries` / `graphql_mutations` if auth exposes GraphQL (so root schema uses registry only).
  - Ensure project uses `plugin_registry.get(...)` for auth-related settings.
- **URLs**
  - Already contributes `v1_urlpatterns` via `plugin.py`.
  - Confirm project uses `plugin_registry.get_all_v1_urlpatterns()` and does not hardcode `include("baseapp_auth...")`.
- **GraphQL shared interfaces**
  - Register **PermissionsInterface** in `AppConfig.ready()` via `GraphQLContributor.register_graphql_shared_interfaces()`.
  - Switch auth to `BaseAppConfig` + `GraphQLContributor`.
  - Other apps must stop importing `PermissionsInterface` from `baseapp_auth` and use `graphql_shared_interface_registry.get_interfaces(["permissions"], default_interfaces)`.
- **Shared services**
  - No other baseapp app currently consumes auth as a service (PermissionsInterface is GraphQL, not a shared service).
  - Add a shared service only if auth exposes reusable behaviour (e.g. token validation, user referral model resolver) that other apps should call via registry.

**Imports / Entry points:** Auth already has plugin entry in root `setup.cfg`. Migrate `apps.py` to `BaseAppConfig` if adding GraphQLContributor.

---

## baseapp_comments

- **Database Migration**
  - Remove concrete `Comment` and `CommentStats` if they should be extendable (keep only abstract/swappable).
  - If all concrete models in baseapp_comments are removed, delete the app’s migrations folder.
- **Database Coupling**
  - **CommentableModel** (and AbstractCommentableModel): remove from this app and from any app that uses it; replace commentable behaviour with DocumentId + CommentStats.
  - **baseapp_profiles:** AbstractComment has `profile` FK via swapper to Profile; remove or replace with a decoupled reference (e.g. DocumentId or project-owned relation).
  - **baseapp_reactions and baseapp_reports:** AbstractComment inherits `ReactableModel` and `ReportableModel`; remove these mixins or replace with a decoupled pattern.
  - **CommentStats** must key off **DocumentId**, not Comment: change `AbstractCommentStats.target` from OneToOne to Comment → OneToOne/FK to `DocumentId`; add migrations and backfill.
  - Ensure comment targets use DocumentId (DocumentIdMixin or `DocumentId.get_or_create_for_object`).
- **Settings**
  - Already in plugin: `AUTHENTICATION_BACKENDS`, `django_extra_settings`, `graphql_queries`, `graphql_mutations`, `graphql_subscriptions`. Add `INSTALLED_APPS` if needed.
  - Ensure no duplicate auth backends in project; project uses slotted `plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_comments")`.
- **URLs**
  - If comments add REST/URLs, contribute via `plugin.py` (`urlpatterns` / `v1_urlpatterns` callbacks).
  - Project uses registry getters only.
- **GraphQL shared interfaces**
  - Already registers **CommentsInterface** via `GraphQLContributor`.
  - Remove direct import of **PermissionsInterface** from `baseapp_auth` in `graphql/object_types.py`; use `graphql_shared_interface_registry.get_interfaces(["permissions"], default_interfaces)` so interfaces are by name only.
- **Shared services**
  - Already registers **comments_count** via `ServicesContributor`; consumers (e.g. baseapp_pages GraphQL) use it.
  - **Consumed by this app:** baseapp_notifications (`send_notification` in comments/notifications.py) and baseapp_reactions (ReactionsInterface). Have comments consume notifications and reactions via shared services once those apps expose them (see baseapp_notifications, baseapp_reactions).
  - Ensure resolvers use `shared_service_registry.get_service("comments_count")` and handle `None`.

**Signals:** Keep `document_created` (or equivalent) handling in `ready()` to create/update CommentStats keyed by DocumentId. Ensure signals use DocumentId, not raw commentable FK.

---

## baseapp_pages

- **Database Migration**
  - Remove concrete Page (or Metadata, etc.) if they should be extendable; keep concrete if they should not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - No coupling with other baseapp apps (only baseapp_core).
  - If Page or other models elsewhere use CommentableModel or inline comment fields, that coupling lives in those apps and must be removed there.
  - Keep DocumentId usage (e.g. `DocumentId.get_or_create_for_object(instance)` in signals) as the decoupled pattern.
- **Settings**
  - Plugin exists but does not contribute `graphql_queries` / `graphql_mutations`. Add them (and `graphql_subscriptions` if any) to **PagesPlugin.get_settings()** so the root schema can use only registry getters.
  - Optionally add `INSTALLED_APPS`, `MIDDLEWARE`, etc. if pages contribute any.
- **URLs**
  - Add `urlpatterns` / `v1_urlpatterns` in plugin only if pages expose URLs; otherwise no change.
- **GraphQL shared interfaces**
  - Already uses `graphql_shared_interface_registry.get_interfaces(["comments"], [RelayNode, PageInterface, PermissionsInterface])`.
  - Replace **PermissionsInterface** import from `baseapp_auth` with requesting `"permissions"` by name: `get_interfaces(["comments", "permissions"], [RelayNode, PageInterface])` so default_interfaces do not include PermissionsInterface (it comes from registry).
- **Shared services**
  - **Consumed by:** baseapp_profiles uses `URLPath` (create, filter, path exists) and profile URL path generation.
  - **Convert:** Expose a shared service (e.g. `url_path`) with methods such as `create_for_target(target, path, is_active)`, `path_exists(path)`, and optionally `suggest_path_for_instance(instance)` so baseapp_profiles does not import URLPath; profiles should call `shared_service_registry.get_service("url_path")` and use that instead.

**Entry points / AppConfig:** Pages uses plain `AppConfig`. Consider `BaseAppConfig` if you add ServicesContributor/GraphQLContributor later. No need for GraphQLContributor on pages (it consumes interfaces; auth/comments provide them).

---

## baseapp_profiles

- **Database Migration**
  - Remove concrete Profile (and ProfileUserRole, etc.) if they should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Mixins from other apps:** AbstractProfile conditionally inherits `BlockableModel` (baseapp_blocks), `FollowableModel` (baseapp_follows), `ReportableModel` (baseapp_reports), `CommentableModel` (baseapp_comments), `PageMixin` (baseapp_pages). Remove all of these; replace behaviour with shared services, DocumentId-based tables, or project-level wiring.
  - **baseapp_pages:** Profile uses `URLPath` from baseapp_pages in `generate_url_path()`, in mutations, and in admin (URLPathAdminInline). Remove this coupling (e.g. consume a `url_path` shared service from pages).
  - **ProfilableModel** is provided by this app and used by baseapp_auth and baseapp_organizations; those apps must stop depending on it (see auth and organizations).
  - Ensure Profile uses DocumentIdMixin (or DocumentId on create) where needed for commentable/document identity.
- **Settings**
  - Add **plugin** for baseapp_profiles if not present: entry point in root `setup.cfg`, `plugin.py` with `get_settings()` contributing `INSTALLED_APPS`, `MIDDLEWARE`, `AUTHENTICATION_BACKENDS`, `GRAPHENE__MIDDLEWARE` as needed, and **graphql_queries** / **graphql_mutations** (and subscriptions if any) so root schema uses registry only.
- **URLs**
  - Contribute via plugin if profiles expose URLs; otherwise no change.
- **GraphQL shared interfaces**
  - Do not import **PermissionsInterface** from `baseapp_auth`. Use `graphql_shared_interface_registry.get_interfaces(["permissions"], [RelayNode, ProfileInterface])` (or equivalent) so permissions interface is by name.
  - If profiles provide a shared interface, add `GraphQLContributor` and register it.
- **Shared services**
  - **Consumed by:** baseapp_organizations uses `ProfileCreateSerializer` to create a profile when creating an organization (OrganizationCreate mutation).
  - **Convert:** Expose a shared service (e.g. `profile_creation`) that wraps profile creation (serializer or create logic) so baseapp_organizations does not import ProfileCreateSerializer; organizations should call `shared_service_registry.get_service("profile_creation")` and use it in the mutation.

---

## baseapp_blocks

- **Database Migration**
  - Remove concrete Block if it should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Coupling to remove:** AbstractBaseBlock (in base.py) has FKs to **Profile** via swapper (baseapp_profiles).
  - Remove this coupling (e.g. reference DocumentId or a project-owned model; do not depend on baseapp_profiles).
- **Settings**
  - Add plugin and entry point if blocks are to be driven by registry. In `plugin.py` contribute `INSTALLED_APPS`, `graphql_queries`, `graphql_mutations`, etc.
  - Project then uses `plugin_registry.get_all_graphql_queries()` and does not import BlocksMutations/BlocksQueries in root graphql.py.
- **URLs**
  - Via plugin if blocks expose URLs.
- **GraphQL shared interfaces**
  - If block types need optional interfaces (e.g. permissions, comments), request them by name via `graphql_shared_interface_registry.get_interfaces([...], default_interfaces)`.
  - No direct interface imports from other packages.
- **Shared services**
  - No other baseapp app consumes blocks as a service.
  - Add a shared service only if blocks expose reusable behaviour (e.g. block counts or block checks) that other apps should call via registry.

---

## baseapp_chats

- **Database Migration**
  - Remove concrete Message, ChatRoom, etc. if they should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Coupling to remove:** Models in `base.py` have FKs to **Profile** via swapper (baseapp_profiles) — e.g. ChatRoom, Message, ChatRoomParticipant, UnreadMessageCount, MessageStatus.
  - Remove this coupling (e.g. reference DocumentId or a project-owned identity; do not depend on baseapp_profiles).
- **Settings**
  - Add plugin: `plugin.py` with `graphql_queries`, `graphql_mutations`, `graphql_subscriptions`, and any `INSTALLED_APPS` / middleware.
  - Root graphql.py should use only registry getters (no direct ChatsQueries, ChatsMutations, ChatsSubscriptions).
- **URLs**
  - Contribute via plugin if chats expose URLs.
- **GraphQL shared interfaces**
  - Use registry by name for any optional interfaces; no cross-package interface imports.
- **Shared services**
  - **Consumed by this app:** baseapp_notifications (`send_notification` in chats/utils.py). Have chats consume notifications via `shared_service_registry.get_service("notifications")` once baseapp_notifications exposes it.
  - No other app currently consumes chats as a service; add one only if chats expose reusable behaviour (e.g. unread counts) for other apps.

---

## baseapp_reactions

- **Database Migration**
  - Remove concrete Reaction if it should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Coupling to remove:** AbstractBaseReaction has FK to **Profile** via swapper (baseapp_profiles).
  - Remove this coupling (e.g. reference DocumentId or project-owned model; do not depend on baseapp_profiles).
  - Reaction target can stay as GenericForeignKey to content; optionally key reaction aggregates by DocumentId.
- **Settings**
  - Add plugin: contribute `graphql_queries`, `graphql_mutations`, and any settings.
  - Root schema uses registry only.
- **URLs**
  - Via plugin if needed.
- **GraphQL shared interfaces**
  - Request by name if reaction types need optional interfaces; no direct imports.
- **Shared services**
  - **Consumed by:** baseapp_comments (ReactionsInterface and ReactableModel on Comment) and baseapp/content_feed (ReactionsInterface and ReactableModel on ContentPost).
  - **Convert:** Expose a shared service (e.g. `reactions_count`) with `get_count(document_id)`, `is_enabled(document_id)` (and optionally default structure) so comments and content_feed can resolve reaction data via `shared_service_registry.get_service("reactions_count")` instead of inheriting ReactableModel and importing ReactionsInterface.
  - Register it in `AppConfig.ready()` via ServicesContributor.

---

## baseapp_ratings

- **Database Migration**
  - Remove concrete Rate if it should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Coupling to remove:** AbstractBaseRate has FK to **Profile** via swapper (baseapp_profiles).
  - Remove this coupling (e.g. reference DocumentId or project-owned model; do not depend on baseapp_profiles).
- **Settings**
  - Add plugin: `graphql_queries`, `graphql_mutations`, and settings.
  - Root schema via registry.
- **URLs**
  - Via plugin if needed.
- **GraphQL shared interfaces**
  - By name only.
- **Shared services**
  - No other baseapp app consumes ratings as a service.
  - Add a shared service only if ratings expose reusable behaviour (e.g. average rating, rate counts) that other apps should call via registry.

---

## baseapp_reports

- **Database Migration**
  - Remove concrete Report, ReportType if they should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - No coupling with other baseapp apps (only internal ReportType and baseapp_core).
  - If reportable content or actor is ever tied to Profile or another app's model, remove that dependency (e.g. use DocumentId or project-owned model).
- **Settings**
  - Add plugin: graphql and settings contributions.
  - Root schema via registry.
- **URLs**
  - Via plugin if needed.
- **GraphQL shared interfaces**
  - By name only.
- **Shared services**
  - **Consumed by:** baseapp_comments (ReportableModel on Comment).
  - If report counts or "is reportable" need to be exposed to other types (e.g. in GraphQL), expose a shared service (e.g. `reports` or `reportable`) with `get_report_count(document_id)` or similar so comments and others resolve via registry instead of inheriting ReportableModel. Otherwise none.

---

## baseapp_follows

- **Database Migration**
  - Remove concrete Follow if it should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Coupling to remove:** AbstractBaseFollow has FKs to **Profile** via swapper (baseapp_profiles) for `actor` and `target`.
  - Remove this coupling (e.g. reference DocumentId or project-owned model; do not depend on baseapp_profiles).
- **Settings**
  - Add plugin: graphql and settings.
  - Root schema via registry.
- **URLs**
  - Via plugin if needed.
- **GraphQL shared interfaces**
  - By name only.
- **Shared services**
  - No other baseapp app consumes follows as a service.
  - Add a shared service only if follows expose reusable behaviour (e.g. follower/following counts) that other apps should call via registry.

---

## baseapp_notifications

- **Database Migration**
  - Remove concrete models if they should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - No coupling with other baseapp apps (only baseapp_core).
  - If notifications ever reference Profile or another app's model directly, remove that dependency.
- **Settings**
  - Add plugin: graphql (mutations, subscriptions) and settings.
  - Root schema via registry.
- **URLs**
  - Via plugin if needed.
- **GraphQL shared interfaces**
  - By name only.
- **Shared services**
  - **Consumed by:** baseapp_comments (`send_notification` in comments/notifications.py), baseapp_reactions (notifications.py), baseapp_chats (utils.py).
  - **Convert:** Expose a shared service (e.g. `notifications`) that provides `send_notification(...)` (or equivalent) so comments, reactions, and chats call `shared_service_registry.get_service("notifications")` instead of importing from baseapp_notifications.
  - Register it in `AppConfig.ready()` via ServicesContributor.

---

## baseapp_organizations

- **Database Migration**
  - Remove concrete Organization if it should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Coupling to remove:** Organization (and related models) conditionally inherit **ProfilableModel** from baseapp_profiles and have FK to Profile.
  - Remove this coupling (e.g. do not inherit ProfilableModel; reference DocumentId or project-owned model; do not depend on baseapp_profiles).
- **Settings**
  - Add plugin: graphql and settings.
  - Root schema via registry.
- **URLs**
  - Via plugin if needed.
- **GraphQL shared interfaces**
  - Currently imports **PermissionsInterface** from `baseapp_auth.graphql.permissions`. Replace with `graphql_shared_interface_registry.get_interfaces(["permissions"], [RelayNode, ...])`.
- **Shared services**
  - No other baseapp app consumes organizations as a service.
  - This app consumes baseapp_profiles (ProfileCreateSerializer); that dependency should be replaced by consuming a `profile_creation` shared service from profiles (see baseapp_profiles).

---

## baseapp_content_feed (baseapp/content_feed)

- **Database Migration**
  - Remove concrete ContentPost, ContentPostImage if they should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - ContentPost has FK to **Profile** via swapper (baseapp_profiles).
  - Abstract model inherits **ReactableModel** from baseapp_reactions.
  - Remove both (e.g. reference DocumentId or project-owned model; do not depend on baseapp_profiles or baseapp_reactions).
- **Settings**
  - Add plugin (under baseapp or as baseapp_content_feed): graphql and settings.
  - Root schema via registry.
- **URLs**
  - Via plugin if needed.
- **GraphQL shared interfaces**
  - By name only.
- **Shared services**
  - No other baseapp app consumes content feed as a service.
  - This app consumes baseapp_reactions (ReactionsInterface, ReactableModel); that should be replaced by consuming a `reactions_count` shared service from reactions (see baseapp_reactions).

---

## baseapp_activity_log (baseapp/activity_log)

- **Database Migration**
  - Remove concrete ActivityLog if it should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - **Coupling to remove:** ActivityLog has FK to **Profile** via swapper (baseapp_profiles).
  - Remove this coupling (e.g. reference DocumentId or project-owned model; do not depend on baseapp_profiles).
- **Settings**
  - Add plugin: graphql (ActivityLogQueries) and settings.
  - Root schema via registry.
- **URLs**
  - Via plugin if needed.
- **GraphQL shared interfaces**
  - By name only.
- **Shared services**
  - No other baseapp app consumes activity log as a service.
  - Add a shared service only if activity log exposes reusable behaviour (e.g. recent activity for an entity) that other apps should call via registry.

---

## baseapp_url_shortening

- **Database Migration**
  - Remove concrete models if they should be extendable; keep if not.
  - If all concrete models are removed, delete the migrations folder.
- **Database Coupling**
  - No coupling with other baseapp apps.
- **Settings**
  - Add plugin if URL shortening is to be registry-driven; contribute URLs and any settings.
  - Project already includes `include("baseapp_url_shortening.urls")` in v1 — move to plugin `v1_urlpatterns` and use `get_all_v1_urlpatterns()` only.
- **URLs**
  - Contribute `v1_urlpatterns` (and `urlpatterns` if any) via plugin callback.
- **GraphQL shared interfaces**
  - N/A unless it exposes types.
- **Shared services**
  - No other baseapp app consumes URL shortening as a service.
  - Add one only if it exposes reusable behaviour (e.g. shorten/resolve) for other apps.

---

## baseapp_wagtail

- **Database Migration**
  - Remove concrete models in wagtail apps (base, medias, etc.) if they should be extendable; keep if not.
  - If all concrete models in an app are removed, delete that app's migrations folder.
- **Database Coupling**
  - No coupling with other baseapp apps in the template.
  - If wagtail page types elsewhere use CommentableModel or FKs to other baseapp apps, remove that coupling (use DocumentId / shared services as needed).
- **Settings**
  - Add plugin if wagtail is registry-driven: INSTALLED_APPS, middleware, graphql, URLs.
  - Project currently does `include(baseapp_wagtail_urls)` — consider contributing via plugin and using `plugin_registry.get_all_urlpatterns()`.
- **URLs**
  - Contribute via plugin so project uses only registry getters.
- **GraphQL shared interfaces**
  - By name only if wagtail types need optional interfaces.
- **Shared services**
  - No other baseapp app consumes wagtail as a service.
  - Add one only if wagtail exposes reusable behaviour (e.g. page resolution, stream field utils) that other apps should call via registry.

---

## baseapp_payments, baseapp_pdf, baseapp_referrals, baseapp_message_templates, baseapp_api_key, baseapp_cloudflare_stream_field, baseapp_drf_view_action_permissions, baseapp_e2e

For each of these:

- **Database Migration**
  - Keep concrete models that should not be extended; remove those that can and should be extendable.
  - If all concrete models in an app are removed, delete that app's migrations folder.
- **Database Coupling**
  - If the app has no model coupling to other baseapp apps, state that.
  - If it has FKs to Profile or other baseapp models (via swapper or direct), or mixins from other apps, describe the coupling and state that it must be removed (e.g. use DocumentId or project-owned models).
- **Settings**
  - Add plugin + entry point in root `setup.cfg` if the app should be registry-driven.
  - Contribute `INSTALLED_APPS`, `graphql_queries`/`graphql_mutations`/`graphql_subscriptions`, URLs, middleware, auth backends as needed.
  - Project uses `plugin_registry.get(...)` and `get_all_*` only.
- **URLs**
  - Contribute via plugin callbacks.
- **GraphQL shared interfaces**
  - Register any provided interfaces in `AppConfig.ready()`; consumers use `graphql_shared_interface_registry.get_interfaces([...], default)` by name.
  - No cross-package interface imports.
- **Shared services**
  - If any other app imports or calls this app's code, expose that as a shared service and have consumers use `shared_service_registry.get_service(name)`.
  - Register in `AppConfig.ready()`; document what the app provides or consumes (see baseapp_notifications, baseapp_pages, baseapp_profiles, baseapp_reactions for examples).

---

## Project-level (testproject) checklist

- **GraphQL root**
  - Remove all direct BaseApp imports for Query/Mutation/Subscription mixins.
  - Use only `plugin_registry.get_all_graphql_queries()`, `get_all_graphql_mutations()`, `get_all_graphql_subscriptions()` and project-specific mixins (e.g. UsersQueries).
- **URLs**
  - Use only `plugin_registry.get_all_urlpatterns()` and `get_all_v1_urlpatterns()`.
  - No hardcoded `include("baseapp_*")` for plugin apps.
- **Settings**
  - Build INSTALLED_APPS, MIDDLEWARE, AUTHENTICATION_BACKENDS, GRAPHENE__MIDDLEWARE (and Constance/extra) from `plugin_registry.get(...)` / `get_all_*` where applicable.
- **Swapper**
  - Keep all `BASEAPP_*_*_MODEL` pointing to project app models.
  - After DB decoupling, ensure CommentStats (and any auxiliary model) is swappable and points to DocumentId-based model.
