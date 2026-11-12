# BaseApp Payments

Integrates Stripe with your Django project over Django REST Framework. It exposes API endpoints to manage Stripe customers, subscriptions, products and payment methods, and a webhook endpoint that keeps your local `Customer` / `Subscription` records in sync with Stripe.

Unlike most BaseApp packages, payments is mostly a **REST** surface. The one exception is the opt-in [card holds](#card-holds), which add GraphQL types when the `graphql` extra is installed. It follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin and contributes its URL patterns through the registry — you do not wire the router by hand.

## How to install

Install the package with `pip install baseapp-backend[payments]`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

The package registers itself as a plugin (see `baseapp_payments.plugin:PaymentsPlugin`).

1. Add `baseapp_payments` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_payments",
    # ...
]
```

2. Add your Stripe credentials to settings:

```python
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
```

## Stripe API version: 2025-05-28.basil

The module sends every Stripe call at API version **`2025-05-28.basil`**
(`DEFAULT_STRIPE_API_VERSION` in `utils.py`; override it with a `STRIPE_API_VERSION`
setting only if you must). It moved from `2025-02-24.acacia` with BA-3483: basil lets
several PaymentIntents pay one invoice, which [paying above the hold](#above-the-hold)
needs.

What you must do when you upgrade:

- **Check your own `STRIPE_API_VERSION` setting.** A project setting overrides the module's
  default. The BaseApp backend template pins `STRIPE_API_VERSION = "2025-02-24.acacia"`;
  change it to `"2025-05-28.basil"` (or remove it). Left on acacia, paying above the hold
  and `attach_payments_to_invoice` don't work.

- **stripe-python 12.2 or later.** The `payments` extra now requires `stripe>=12.2,<15`:
  `Invoice.attach_payment`, which the [invoice helper](#one-invoice-for-every-payment)
  uses, first shipped in 12.2.0 (the release pinned to `2025-05-28.basil`);
  `InvoicePayment.list` shipped in 12.0.0.

- **Set your webhook endpoint to the same version.** Stripe renders each event at the
  *endpoint's* API version, not the one this module requests. In the Dashboard
  (Developers → Webhooks → your endpoint → *Update API version*) pick `2025-05-28.basil`,
  or create a new endpoint at that version and swap `STRIPE_WEBHOOK_SECRET`. The Stripe
  CLI (`stripe listen`) forwards events at your account's default API version (and
  `--latest` at Stripe's newest, past basil), so locally upgrade the test account's
  default to basil in Workbench.
- **Subscribe the endpoint to the card hold events** (below) if you use holds: the
  difference above a hold is reconciled from `payment_intent.succeeded` /
  `payment_intent.payment_failed`.
- **Check your own Stripe code** for what basil removed (the module's own reads are
  handled): `subscription.current_period_start/end` moved to `subscription.items.data[]`;
  `invoice.payment_intent`, `invoice.charge` and `invoice.paid` are gone (use
  `invoice.payments`, `invoice.confirmation_secret`, `invoice.status`);
  `invoice.subscription` is `invoice.parent.subscription_details.subscription`; invoice
  lines lost `price`, `plan` and `type` (`pricing.price_details.price`, `parent.type`);
  `PaymentIntent.invoice` / `Charge.invoice` are gone; a lapsed authorization is cancelled
  with `cancellation_reason="expired"` (was `automatic`); and a partial capture or a
  cancel no longer creates a Refund or a second balance transaction.
- **Frontend:** a subscription's `client_secret` now comes from the latest invoice's
  `confirmation_secret`; the REST payload keeps the same `client_secret` and
  `current_period_end` fields, so nothing changes for API clients.
- **Card holds:** run `makemigrations` for your concrete `CardHold` (new columns, below),
  and backfill `payment_status` for holds captured or charged before the upgrade:

  ```python
  CardHold.objects.filter(
      Q(status="captured") | Q(charged_at__isnull=False)
  ).update(payment_status="paid")
  ```

## Customer Integration

A Customer represents any entity (such as a User, Organization, or any model with an email attribute) that will be billed through Stripe.

By default we have configured to work with profiles, meaning it will get the email through `profile.target.email`, but you can also use other models if the model has a email field, simply changing the STRIPE_CUSTOMER_ENTITY_MODEL to your chosen model. Be aware that this model must have a ContentType though.

With a provided `entity_id`, the `StripeCustomerSerializer` creates a customer in Stripe and our Customer model links them via the `remote_customer_id` and `entity_id`.

## Subscription Management

The Subscription model stores Stripe subscription details including:

`customer` (a foreign key to the Customer that owns it)
`remote_subscription_id`

## Creating a Subscription

To create a subscription, use the `payments/stripe/subscriptions/` (assuming your route is registered at `payments/`) endpoint. A validation will check that no active subscription exists for the same product and price id, to reduce duplicate subscriptions, and then creates a new subscription through the Stripe API. It returns the new `remote_subscription_id` upon success.

## Configure URL Patterns

The plugin contributes its routes via `v1_urlpatterns`, so your project's `urls.py` composes them through the registry - there is no manual `include` of the payments router:

```python
from baseapp_core.plugins import plugin_registry

v1_urlpatterns = [
    # ... project v1 patterns ...
    *plugin_registry.get_all_v1_urlpatterns(),
]

urlpatterns = [
    path("v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
    # ...
]
```

This mounts the payments router under `v1/payments/` (see [API endpoints](#api-endpoints)).

4. Define the concrete `Customer` / `Subscription` models (see [models](#models)) and point the swapper settings at them:

```python
BASEAPP_PAYMENTS_CUSTOMER_MODEL = "payments.Customer"
BASEAPP_PAYMENTS_SUBSCRIPTION_MODEL = "payments.Subscription"
```

## Customer entity model

A `Customer` links any local entity (a `Profile`, `User`, `Organization`, or any model with an `email`) to its Stripe customer record via `remote_customer_id`. Which model is treated as the billable entity is a **Constance** setting (changeable at runtime), defaulting to `profiles.Profile`:

```python
# Constance config — default "profiles.Profile"
STRIPE_CUSTOMER_ENTITY_MODEL = "profiles.Profile"
```

When a customer is created (via the API or the `customer.created` webhook), the entity is resolved from this model and linked to the Stripe customer.

### Who may bill an entity

Authorization for every customer and subscription route runs through
`baseapp_payments.permissions.is_entity_owner`, which delegates to the callable named by
`BASEAPP_PAYMENTS_ENTITY_OWNER_CHECK`:

```python
# settings.py — default
BASEAPP_PAYMENTS_ENTITY_OWNER_CHECK = "baseapp_payments.permissions.default_entity_owner_check"
```

The default answers for the two entity models the package can reason about:

| Entity | Billable by |
| --- | --- |
| `baseapp_profiles` Profile | its `owner`, the user whose own profile it is, or an active **ADMIN** member |
| The user model | that user |
| Anything else | **nobody** |

`baseapp_profiles` is optional — the Profile branch is skipped entirely when the app is
not installed.

> ### ⚠️ Pointing `STRIPE_CUSTOMER_ENTITY_MODEL` at your own model
>
> The default check denies every request for an entity model it does not recognise, so
> set `BASEAPP_PAYMENTS_ENTITY_OWNER_CHECK` to your own `check(entity, user) -> bool`
> alongside it. It is only consulted for authenticated users, so it never has to handle
> `AnonymousUser`.
>
> Denying is deliberate. The previous behaviour compared the entity's pk to the user's,
> which made organization 5 appear to be owned by user 5.

## Models

`BaseCustomer` and `BaseSubscription` are abstract + swappable, and the package ships **no** concrete models or migrations — your project must subclass them and point the swapper settings at the concrete models (see [How to develop](#how-to-develop)).

| Abstract | Concrete reference | Purpose |
|---|---|---|
| `BaseCustomer` | `Customer` | Generic-FK `entity` (the billable model) + `remote_customer_id`. |
| `BaseSubscription` | `Subscription` | `customer` (FK to the concrete Customer) + `remote_subscription_id`. |

> **Important:** `BaseCustomer.save()` requires the concrete model to declare `tracker = FieldTracker(["entity"])` (from `model_utils`) — it uses the tracker to populate `entity_type` / `entity_id` when the generic `entity` changes, and raises a `RuntimeError` if it's missing.

## Upgrading: Subscription.customer

`Subscription` used to carry the Stripe customer id as a string, `remote_customer_id`.
It now points at the local `Customer` with a foreign key, because the webhook has to
resolve the local row and matching on the Stripe id silently created orphans when it
missed.

A project that already has subscription rows needs a migration that resolves each one
*before* the old column is dropped — the mapping only exists until then. The reference
implementation is `0002_subscription_customer_fk` in the testproject:

1. add the FK as `null=True`
2. `RunPython` to set `customer` from `remote_customer_id`
3. alter the FK to non-null
4. remove `remote_customer_id`

Two things that matter in step 2. Resolve the swappable model with
`apps.get_model(settings.BASEAPP_PAYMENTS_CUSTOMER_MODEL)` rather than a hardcoded
label. And **fail** on a subscription whose `remote_customer_id` matches no `Customer`,
rather than defaulting it — a subscription attached to the wrong customer bills the
wrong card, and once the column is gone there is nothing left to reconcile against.

The migration is forward-only. Reversing re-adds `remote_customer_id` as a non-null
column with no default, which the database rejects on any table that still has rows.

## API Endpoints

All routes are mounted under `v1/payments/`. **The router is `DefaultRouter(trailing_slash=True)`, so every path ends in `/`** - an unslashed request does not resolve and only survives via Django's `APPEND_SLASH` redirect, which drops the body on writes.

Authenticated endpoints require `IsAuthenticated` plus an object permission; the webhook is unauthenticated (verified by Stripe signature instead).

| Method & path | Action |
|---|---|
| `GET v1/payments/stripe/subscriptions/?entity_id=...` | List an entity's subscriptions (`?status=` widens past the default `active`). |
| `POST v1/payments/stripe/subscriptions/` | Create a subscription (rejects a duplicate active subscription for the same product/price). |
| `GET v1/payments/stripe/subscriptions/{remote_subscription_id}/` | Retrieve subscription details from Stripe. |
| `PATCH v1/payments/stripe/subscriptions/{remote_subscription_id}/` | Update a subscription. |
| `DELETE v1/payments/stripe/subscriptions/{remote_subscription_id}/` | Cancel a subscription. |
| `POST v1/payments/stripe/customers/` | Create a customer. |
| `GET v1/payments/stripe/customers/{entity_id}/` | Retrieve a customer by entity relay id, or `me` for the current user. |
| `GET v1/payments/stripe/customers/{entity_id}/invoices/` | List the customer's invoices (paginated). |
| `GET v1/payments/stripe/customers/{entity_id}/payment-methods/` | List the customer's payment methods. |
| `POST v1/payments/stripe/customers/{entity_id}/payment-methods/` | Create a `SetupIntent` to attach a payment method. |
| `PUT v1/payments/stripe/customers/{entity_id}/payment-methods/{payment_method_id}/` | Update a payment method. |
| `DELETE v1/payments/stripe/customers/{entity_id}/payment-methods/{payment_method_id}/` | Detach a payment method. |
| `GET v1/payments/stripe/products/` | List Stripe products. |
| `GET v1/payments/stripe/products/{product_id}/` | Retrieve a product. |
| `POST v1/payments/stripe/webhooks/` | Stripe webhook receiver. |

Payment-method and invoice routes are nested under the customer, so the entity in the URL is authorized through `DRFCustomerPermissions` before Stripe is called.

## Stripe webhooks

`StripeWebhookViewset` verifies the Stripe signature against `STRIPE_WEBHOOK_SECRET` and dispatches to `StripeWebhookHandler`, which handles:

- `customer.created` — create the local `Customer` (resolving the entity from `STRIPE_CUSTOMER_ENTITY_MODEL`).
- `customer.deleted` — delete the local `Customer`.
- `customer.subscription.created` — create the local `Subscription`.
- `customer.subscription.deleted` — delete the local `Subscription`.
- `payment_intent.amount_capturable_updated`, `payment_intent.canceled`,
  `payment_intent.succeeded`, `payment_intent.payment_failed` — with card holds enabled, a
  PaymentIntent whose metadata carries `card_hold_id` is reconciled with its hold (see
  [Lost answers and reconciliation](#lost-answers-and-reconciliation)). Any other
  PaymentIntent, or every one without card holds, is acknowledged and ignored.

### Stripe dashboard configuration

**Production:** In your [Stripe Dashboard](https://dashboard.stripe.com) → **Developers → Webhooks → Add endpoint**, point the endpoint at `https://yourdomain.com/v1/payments/stripe/webhooks/`, subscribe to the events above (the four `payment_intent.*` ones only if you use card
holds), then copy the **Signing secret** into `STRIPE_WEBHOOK_SECRET`.

**Local development:** Use the [Stripe CLI](https://stripe.com/docs/stripe-cli):

```bash
stripe login
stripe listen --forward-to localhost:8000/v1/payments/stripe/webhooks/
```

The CLI prints a `whsec_...` secret — set it as `STRIPE_WEBHOOK_SECRET` locally.

## StripeService

`StripeService` (in `baseapp_payments.utils`) encapsulates all Stripe API calls — customers, subscriptions (including incomplete subscriptions), products, payment methods, setup/payment intents, prices and invoices — and is used internally by the serializers, viewsets and webhook handler so Stripe communication stays in one place.

## Admin

Both swapped models (and, when enabled, the card hold) are registered in the Django admin (`CustomerAdmin`, `SubscriptionAdmin`) with `remote_*` ids read-only, for easy inspection of Stripe-linked records.

## Card holds

> **Before you enable card holds, check that your business fits Stripe's rules.** This module places authorizations ("holds") and captures them later. It also saves cards to place holds without the customer present. Stripe and the card networks restrict both. Baseapp can't check these for you.
> - **Business eligibility.** Stripe won't serve some businesses, and serves restricted ones only with its written approval ([Prohibited and Restricted Businesses](https://stripe.com/legal/restricted-businesses)). Check your category before building on this.
> - **Holds expire.**
>   - Customer-initiated online card holds last about 7 days. Visa holds placed without the customer present (merchant-initiated) last 5 days, and Stripe's exact window is 4 days 18 hours.
>   - Stripe decides whether the customer was present from the transaction's signals, not from the `off_session` flag alone ([Place a hold](https://docs.stripe.com/payments/place-a-hold-on-a-payment-method)).
>   - The deferred-hold window is therefore capped at 4 days (and defaults to 4). A hold placed by the first sweep of D−4 (about 00:15) must be captured before about 18:00 on D, or its `capture_before` lapses and `capture()` charges afresh instead.
>   - The module reads the real expiry from `capture_before` and relies on it, never on the window. Capture early on the target's date.
> - **Longer holds are limited.**
>   - Extended authorizations of up to 30 days require IC+ pricing and apply only when the customer is present.
>   - They depend on your merchant category: Visa outside hotels, lodging, car rental and cruise lines costs an extra 0.08%; Amex and Discover cover only a few travel categories.
>   - The networks mean them for cases where the final amount isn't known yet ([Extended authorization](https://docs.stripe.com/payments/extended-authorization)).
>   - This module doesn't request them.
> - **One capture per hold.** A partial capture releases the rest. Capturing more than was held (overcapture) is only available for some card payments. When the final amount is higher, the module captures the whole hold and charges the difference to the same card, off-session (your terms must cover that second charge too); an expired hold is released and the card charged again for the full amount.
> - **Customer consent for saved cards and off-session holds.**
>   - To charge or hold a card later without the customer present, your terms must say when it will happen and how the amount is set. The customer must accept them, and you must keep a record ([Save and reuse](https://docs.stripe.com/payments/save-and-reuse)).
>   - With deferral on, a far-off target's hold is placed off-session, `window_days` before its date, for the price at that moment plus the buffer. Your terms must cover exactly that: the hold, its timing, and that the amount may differ from the one shown at checkout.
>   - The module records nothing about consent; that's on your app.
> - **Statements.** Some banks show a hold as a charge, which confuses customers. Use clear statement descriptors and copy.
> - Stripe's rules change without notice. Re-check these pages before going live. This is guidance, not legal advice.

A card hold authorizes a customer's card for something you will charge later (an order, a
booking, a reservation: the hold's *target*), then either captures the final amount from it
or releases it. It is part of `baseapp_payments` itself: the model in `models.py`, the
placing/release/capture services in `holds.py`, the target hooks in `hold_targets.py`, the
Stripe helpers in `utils.py`, tasks, signals, admin and permissions in their usual modules,
and the GraphQL types in `graphql/`.

What it does today:

- **Holds or a direct charge, per target model.** Each adapter declares `uses_holds`. With
  holds, the card is authorized ahead of the date and captured on it. Without them, the card
  is only saved at checkout and charged directly on the date. Either way the project calls
  the same `capture()` on the date. See [Holds or a direct charge](#holds-or-a-direct-charge).
- **Only for targets charged in the future.** A target with no date, or dated today or
  earlier, takes no hold and saves no card: placing answers `charge_now`, and the project
  charges it directly while the customer is present.
- **Placing, with the customer present.** Your own create mutation calls
  `authorize_on_session(...)`. It reads the card from Stripe (never from the client), prices
  the target through your adapter, refuses if the price differs from what the page showed,
  and creates a manual-capture PaymentIntent (`payment_method_types=["card"]`). If Stripe asks
  for 3D Secure, the result is `requires_action` with a client secret; after the customer
  authenticates, your mutation calls `complete_on_session(...)`.
- **One target per attempt.** The client generates an `attemptId` once per checkout and
  keeps it across retries and the 3D Secure second pass. Different attempt ids mean
  different orders, so renew it only after `declined`, `changed` or `refused` (a refused
  attempt ended without a target, so retrying it only answers `declined`). Every pass first answers
  from the attempt's hold rows, before any check or Stripe call, so this holds beyond
  Stripe's 24-hour idempotency window: an attempt that placed gets its target back (even
  after a later re-arm of that target), one that ended without a target answers
  `declined`, and one still pending carries on. The Stripe idempotency key is
  `{prefix}-hold-{user}-{attempt}`. `find_attempt(user, attempt_id)` returns that
  answer (or `None` to go on), and `find_placed(user, attempt_id)` just the target an
  attempt placed (authorized, scheduled or card saved), or `None`: use it to answer a
  retried create mutation before building anything.
- **Linking under a lock.** Your `link(hold)` callable creates (or returns) the target inside
  a savepoint, under the hold's row lock. The target is re-checked there (not cancelled, not
  done with the card, still in `filter_holdable`) and re-priced through your adapter, and
  the PaymentIntent amount must equal the hold amount. The same checks run once before
  Stripe is called, so a target that can't take a hold costs no PaymentIntent. Any refusal rolls back what
  `link` wrote and releases the hold. A hold already linked is never cancelled by placing.
- **Releasing.** Call `release_target_holds_on_commit(target)` from every path that cancels a
  target. The `release_card_hold` task cancels the PaymentIntent, retrying Stripe's transient
  errors up to 12 times (backoff capped at 1500 s). Stripe is asked even for a hold past its
  expiry: an authorization it still holds is cancelled, one it already cancelled is confirmed,
  and one it reports captured is marked `captured` with the amount received, never released.
  Each release records `release_reason` (`abandoned`, `cancelled`, `card_released`,
  `declined`, `for_charge`, `lapsed`, `not_holdable`, `rescheduled`); a hold released
  `for_charge`, or charged instead, is never re-armed. `status=released` can be written
  before Stripe confirms the cancel; `release_confirmed_at` records the confirmation, and
  until then the sweep re-drives the cancel (until the authorization expires), so a broker
  outage or exhausted retries never strand an authorization. Every authorization that is
  being cancelled stays on its row like this, the current PaymentIntent with its expiry,
  including one a deferred placement made for a target that can no longer take it. A hold
  a live `capture()` claims is skipped and released by a later sweep. Deleting a
  registered target releases its open holds automatically.
- **Capturing.** See [Capturing on the date](#capturing-on-the-date). A final amount
  above a live hold captures the hold in full and charges the difference
  ([Above the hold](#above-the-hold)); every hold records a
  [payment status](#payment-status-and-signals) and [Stripe's fees](#fees).
- **Card removal guard.** `card_in_use(user, payment_method_id)` /
  `in_use_payment_method_ids(user)` tell your card-removal path which cards a hold still needs.
- **No Stripe key, no Stripe calls.** Without `STRIPE_SECRET_KEY`, every task is a no-op and
  placing declines. A bad or revoked key (`AuthenticationError`, `PermissionError`) is never
  read as a decline: placing answers `in_progress`, a deferred hold stays `scheduled`, and both
  log an error.

- **Placing later, without the customer present** (off by default). See
  [Holds placed later](#holds-placed-later-the-window).

### Enabling it

Card holds are opt-in. A project that only uses the REST endpoints above sets nothing and
gets no hold behaviour, no extra admin and no GraphQL types. The plugin's three Constance
keys and its sweep beat entry are still listed for every project: plugin settings are built
before your settings can be read. Without a card hold model they are never read, and the
sweep returns before any query.

The model is needed whether or not your targets use holds: it stores the saved card and
the charge record that keep a direct charge to one (see below).

1. Add the concrete model next to your `Customer`, and run `makemigrations`:

   ```python
   from baseapp_payments.models import AbstractCardHold


   class CardHold(AbstractCardHold):
       class Meta(AbstractCardHold.Meta):
           pass
   ```

2. Point the settings at it and register your targets:

   ```python
   BASEAPP_PAYMENTS_CARDHOLD_MODEL = "payments.CardHold"
   BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {
       "orders.Order": "apps.orders.card_holds.OrderHoldTarget",
   }
   # Give every project sharing a Stripe account its own prefix.
   BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX = "acme"
   ```

3. In each adapter, declare `uses_holds` and, with holds, `hold_amount_mode` (see
   [Holds or a direct charge](#holds-or-a-direct-charge)). Neither has a default.

4. Merge the plugin's Constance keys (`plugin_registry.get_all_constance_config()`) and Celery
   beat entries (`plugin_registry.get_all_celery_schedules()`) into your settings, if your
   project doesn't already.

| Setting | Default | Meaning |
|---|---|---|
| `BASEAPP_PAYMENTS_CARDHOLD_MODEL` | unset (off) | The concrete card hold model. |
| `BASEAPP_PAYMENTS_CARD_HOLD_TARGETS` | `{}` | `{"app_label.Model": "dotted.path.Adapter"}` |
| `BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX` | `"baseapp"` | Prefix of every idempotency key. |
| `BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT` | `True` | Placing, capturing and `release_for_charge` raise `CardHoldInTransaction` inside a transaction. Set `False` only in a test suite that wraps every test in one (see [Placing from your mutation](#placing-from-your-mutation)). |

**Customers with holds can't be deleted.** `CardHold.customer` is `on_delete=PROTECT`, on
purpose: a hold row, in any status, is payment history. Deleting a user with any hold row
raises `ProtectedError`, so `baseapp_auth`'s account deletion task fails for them. Decide in
your project what deleting such an account means (anonymize it, or keep it inactive).

| Constance key | Default | Meaning |
|---|---|---|
| `CARD_HOLDS_BUFFER_PERCENT` | `10` | For `hold_amount_mode = "value_plus_buffer"` only: `held = ceil(value × (1 + buffer/100))`. |
| `CARD_HOLDS_WINDOW_DAYS` | `4` | Days before the target's date to place a deferred hold; clamped to 1–4. |
| `CARD_HOLDS_DEFERRAL_ENABLED` | `False` | Whether far-off targets get their hold later, off-session. Only for adapters with `uses_holds = True`. |

An adapter's `buffer_percent()` / `window_days()`, or a `buffer_percent` returned with the
amount, override the Constance values for that target. With `hold_amount_mode = "value"` no
buffer is applied, whatever any of them say.

### Holds or a direct charge

Every adapter declares two things, with no default. `get_targets()` (run when the app
starts, and by every card hold service) raises `ImproperlyConfigured` when one is missing:

| Declaration | Values | Meaning |
|---|---|---|
| `uses_holds` | `True` / `False` | Whether this target model's card is authorized ahead of its date. Required. |
| `hold_amount_mode` | `"value"` / `"value_plus_buffer"` (`HoldAmountMode`) | What a hold covers: the value alone, or the value plus `CARD_HOLDS_BUFFER_PERCENT` (or your `buffer_percent()`). Required when `uses_holds = True`; ignored otherwise. |

```python
from baseapp_payments.hold_targets import BaseHoldTarget, HoldAmountMode


class OrderHoldTarget(BaseHoldTarget):
    model = Order
    uses_holds = True
    hold_amount_mode = HoldAmountMode.VALUE_PLUS_BUFFER


class BookingHoldTarget(BaseHoldTarget):
    model = Booking
    uses_holds = False  # save the card, charge it on the date
```

**When nothing is held.** Placing first asks your adapter's `target_date(target)`. A target
with no date, or dated today or earlier, is charged now: `authorize_on_session` answers
`charge_now` before any Stripe call, writes no row and links nothing. Charge it yourself, on
session, while the customer is there (a normal automatic-capture PaymentIntent, with its own
3D Secure). This applies to both kinds of adapter, and only at placement: a target whose date
later moves to today keeps what it has.

**`uses_holds = False`: a direct charge on the date.** For a target charged after today,
`authorize_on_session` authorizes nothing. It saves the card with an off-session SetupIntent
(the same pass as a deferred hold: `requires_action` with `intentType` `setup_intent`, then
`complete_setup_on_session`) and links a `saved` row, answering `card_saved`. On the date,
call `capture(hold_id, amount_cents, charge=...)` as for any hold: there is nothing to
capture, so it calls your `charge(idempotency_key=...)` once, with the same claim and key as
a charge-instead (`{prefix}-charge-{hold id}-{n}`), and records `charged_at`. A retry answers
`charged` from the database. `CARD_HOLDS_DEFERRAL_ENABLED`, the window and the buffer play
no part. Cancelling the target releases the row with no Stripe call, and the card is no
longer in use.

**`uses_holds = True`: a hold.** Placed at checkout (on-session) when the date is within
the window, or, with `CARD_HOLDS_DEFERRAL_ENABLED`, saved and placed off-session `window_days`
before the date. With deferral off, a target further out is held at checkout anyway, and
`capture_before` decides whether the hold still stands on the date.

### Registering a target

A hold attaches to its target through `DocumentId` (`target_document`, one hold per target),
so the target model should use `DocumentIdMixin`. Register the concrete model: a proxy in
`BASEAPP_PAYMENTS_CARD_HOLD_TARGETS` raises `ImproperlyConfigured`. Proxies of a registered
model are handled as it (their deletes release its holds too).

**One row per target, re-armed after a release.** When an existing target whose hold is
`released` needs a new one (pass the saved target to `authorize_on_session(target=...)`, so
it is locked before the holds), the same row is re-armed: the new PaymentIntent, card,
amounts, expiry, status and attempt replace the old ones, the failure and deferred-placement
claim fields are cleared, and the replaced PaymentIntent and attempt ids are appended to
`previous_payment_intent_ids` / `previous_attempt_ids` (so the old attempt still finds its
target). Only the target object that was locked is re-armed: a `link` that returns some
other existing target is refused. A hold that is still open (`pending`, `authorized`) or
`captured` refuses (`refused`), and so do `failed` and `scheduled`: a failed deferred hold is
final, and nothing (the sweep, a date or window change) re-arms it, not even once staff
cancelled it. A hold released `rescheduled` is moved back to `scheduled` by `reschedule`
only. With deferral on, a far-off target's hold is re-armed `scheduled` (and a `saved` card
`saved` again, for an adapter without holds). A release still queued for the old
authorization only ever cancels that old PaymentIntent. A `released` hold whose cancel Stripe
hasn't confirmed yet (`release_confirmed_at` empty) is never re-armed as it is: the first pass
asks Stripe to cancel it first, and answers `in_progress` until Stripe confirms, so the old
authorization is never dropped while it may still be live.

Subclass `BaseHoldTarget`, declare `uses_holds` and `hold_amount_mode` (see
[Holds or a direct charge](#holds-or-a-direct-charge)), and implement what only your
project knows:

```python
from baseapp_payments.hold_targets import BaseHoldTarget, HoldAmount, HoldAmountMode


class OrderHoldTarget(BaseHoldTarget):
    model = Order
    uses_holds = True
    hold_amount_mode = HoldAmountMode.VALUE_PLUS_BUFFER

    def owner(self, order):
        return order.customer

    def hold_amount(self, order, card=None):
        # `order` may be unsaved (the check before Stripe is called). `card` is the card
        # being held, for prices that depend on it.
        return HoldAmount(estimated_cents=order.quote(card).total_cents)

    def target_date(self, order):
        return order.delivery_date

    def filter_cancelled(self, queryset):
        return queryset.filter(status=Order.Status.CANCELLED)

    def filter_card_released(self, queryset):
        # Done with the card: charged or settled. Their open hold is released.
        return queryset.filter(paid_at__isnull=False)

    def charge_may_be_in_flight(self, order):
        return order.charge_claimed_recently()

    def cancel(self, order, actor):
        order.cancel(by=actor)
```

| Hook | Default | Used for |
|---|---|---|
| `uses_holds` | required | Authorize ahead of the date, or save the card and charge on it. |
| `hold_amount_mode` | required with holds | `"value"` or `"value_plus_buffer"`. |
| `owner(target)` | required | Only the owner's hold is linked to a target. |
| `hold_amount(target, card)` | required | Pricing before Stripe and again under the lock. |
| `target_date(target)` | required | The date it is charged on: `None`, today or earlier answers `charge_now`. Also deferred holds and `holdOn`. |
| `lock(target_pk)` | `select_for_update()` on the model | Always taken before the hold's lock. |
| `filter_cancelled(qs)` | required | Release and the sweep. |
| `filter_card_released(qs)` | none | The sweep releases these holds, unless a charge is in flight. |
| `charge_may_be_in_flight(target)` | `False` | Keeps a hold while your charge may still run. |
| `filter_holdable(qs)` | all | Placing; a scheduled hold is placed only while its target is in it. |
| `cancel(target, actor)` | required for deferral | Staff cancelling a failed deferred hold. |
| `staff_recipients(target)` | active users with `change_cardhold` (and superusers) | Who hears about a failed deferred hold. |
| `notify_hold_failed(target, hold)` | emails `staff_recipients` | How they hear about it. |
| `window_days()` / `buffer_percent()` | Constance | Per-model defaults. |

### Placing from your mutation

```python
from baseapp_payments.graphql.mixins import (
    CardHoldPayloadMixin,
    CardHoldPaymentInputMixin,
    card_hold_payload,
)
from baseapp_payments.holds import (
    HoldRefused,
    PlacementStatus,
    authorize_on_session,
    complete_on_session,
)


class OrderCreate(CardHoldPayloadMixin, RelayMutation):
    class Input(CardHoldPaymentInputMixin):
        expected_amount_cents = graphene.Int(required=True)
        ...

    @classmethod
    def mutate_and_get_payload(cls, root, info, **input):
        user = info.context.user
        order = build_order(user, input)  # validated, unsaved

        def link(hold):
            # Runs under the hold's lock, inside a savepoint. No Stripe calls here.
            if not slot_still_free(order):
                raise HoldRefused([ErrorType(field="slot", messages=["Fully booked."])])
            order.save()
            return order

        common = dict(
            user=user,
            attempt_id=input["attempt_id"],
            stripe_customer_id=customer_id_of(user),
            expected_amount_cents=input["expected_amount_cents"],
        )
        if input.get("payment_intent_id"):
            result = complete_on_session(input["payment_intent_id"], link, **common)
        else:
            result = authorize_on_session(
                payment_method_id=input["payment_method_id"], target=order, link=link, **common
            )
        # Return the card hold payload on every answer, errors included: clients read
        # `holdStatus` to retry `in_progress` and to renew the attempt after `declined`,
        # `changed` or `refused`. Without it they can't tell those apart.
        payload = card_hold_payload(result)
        if result.status == PlacementStatus.CHARGE_NOW:
            # Your own on-session charge; nothing was held.
            return cls(order=charge_now(order), **payload)
        if result.status not in (
            PlacementStatus.PLACED,
            PlacementStatus.CARD_SAVED,
            PlacementStatus.REQUIRES_ACTION,
        ):
            return cls(errors=errors_for(result), **payload)
        return cls(order=result.target, **payload)
```

Always return `card_hold_payload(result)`, including alongside `errors`. The frontend's
`useCardHoldPlacement` decides what to do next from `holdStatus` alone.

Call both outside a transaction (exclude this mutation from `ATOMIC_MUTATIONS` /
`ATOMIC_REQUESTS`): the pending hold row is committed as soon as the PaymentIntent exists, so
the sweep can release it if the request dies. When the connection isn't in autocommit mode
(`transaction.get_autocommit()`, false inside `transaction.atomic()`) both raise
`CardHoldInTransaction` instead of running. A test suite that wraps every test in a
transaction sets `BASEAPP_PAYMENTS_CARD_HOLD_REQUIRE_AUTOCOMMIT = False` and checks the guard
in transactional tests.

A 5xx or 429 from Stripe while authorizing is retried once with the same key, then answers
`in_progress`, never `declined`: it may hide an authorization Stripe made. The attempt's
`pending` row is written (and committed) before the PaymentIntent is created, with the key
and when it was first sent, and the PaymentIntent's metadata names it (`card_hold_id`).
Stripe saves a 5xx for its idempotency key and replays it for at least 24 hours, then may
forget the key, so a retry is never sent blind for long: an attempt behind one answers
`in_progress` (a webhook recording the authorization lets the next retry carry on with it,
without sending the key again), and once the key is 23 hours old it is reconciled instead
(see [Lost answers and reconciliation](#lost-answers-and-reconciliation)); the attempt then
answers `declined`. Let the customer start over with a new attempt id (a new order). A bad or revoked API key answers
`in_progress` too, logged as an error, and isn't retried: Stripe ran nothing, so the same
attempt works once the key is fixed.

On the second pass, a PaymentIntent still waiting (`requires_action`,
`requires_confirmation`, `processing`) answers `in_progress` and is left alone; only a
finished one (`canceled`, `requires_payment_method`) is released.

| Result | Meaning for the page |
|---|---|
| `placed` | Done; `result.target` is the placed target. |
| `card_saved` | Done (`uses_holds = False`); nothing is held, the card is saved, and `capture()` charges it on the date. |
| `charge_now` | No hold needed: the target has no date after today. Nothing was written; charge it yourself, now. |
| `requires_action` | Confirm `clientSecret` with Stripe.js, then resend with `paymentIntentId`. |
| `declined` | Ask for another card, with a new `attemptId`. |
| `in_progress` | Already being placed, Stripe gave no usable answer, or the target's previous hold is still being cancelled: wait and retry with the same `attemptId`. |
| `changed` | Same `attemptId`, different parameters: renew it and resend. |
| `amount_changed` | The price changed: show the new one. |
| `refused` | Your `link` raised `HoldRefused` (`result.errors` is what you passed), or the target already has a hold that can't be re-armed. |
| `scheduled` | Done; nothing is held yet. The hold is placed on `result.hold_on`: tell the customer. |

`card_hold_payload(result)` also returns `hold_status` (the result above) and `hold_on`, for
`CardHoldPayloadMixin`'s `holdStatus` / `holdOn`.

### Capturing on the date

On the target's date, with or without a hold, call
`capture(hold_id, amount_cents, charge=...)`. Call it outside a transaction, like placing:

- It first claims the hold (a conditional UPDATE, committed before any Stripe call). A
  concurrent call answers `in_progress`, and so does `release_for_charge`, which takes the
  same claim: the two never run at once.
- It captures when the hold covers the amount (authorized, unexpired, `0 < amount <= held`),
  with the idempotency key `{prefix}-capture-{PaymentIntent}` (one per authorization), and
  records `captured_amount_cents` / `captured_at`. A hold already captured answers `captured`
  again for the same amount (`not_captured` for another) from `captured_amount_cents`, and
  never charges; Stripe is read only when no amount was recorded. `capturable_hold(hold_id,
  amount_cents)` tells you, from the database only, whether that amount would be captured
  from the hold alone (to show the customer which way it goes, say).
- Above an authorized, unexpired hold, it captures the **whole** hold, then charges the
  difference to the same card: see [Above the hold](#above-the-hold). Your `charge` is not
  called on that path.
- An amount of 0 releases the hold (`card_released`) and charges nothing: `nothing_due`,
  and the target is `paid`, as nothing is owed (`in_progress` while a placement or an
  unconfirmed cancel is under way, and the status is left as it is). It never re-runs
  a charge an earlier call claimed and didn't finish (it may have run): it answers
  `in_progress`, leaves the claim as it is and logs an error; check that charge in Stripe and
  settle it by hand. A negative amount raises `ValueError`.
- Otherwise it calls your `charge(idempotency_key=...)` for the **full** amount, with
  `{prefix}-charge-{hold id}-{n}` (pass that key to Stripe), but only from a state where
  nothing of ours is held and nobody else may have charged. Return the PaymentIntent from
  `charge`: its id and amount are recorded (`charge_payment_intent_id`,
  `charge_amount_cents`) for the [invoice helper](#one-invoice-for-every-payment) and
  [fees](#fees) (create it with `expand=["latest_charge.balance_transaction"]` and the fee
  is recorded at once). The amount asked is recorded as `charge_amount_cents` before your
  `charge` runs, so the totals count the payment even when it returns something else. The
  states:
  - an open hold this call releases (Stripe confirms the cancel, or reports that it lapsed by
    itself: `charge_expired_for_capture`, or `canceled` with `cancellation_reason`
    `automatic`);
  - a `scheduled` hold never placed, a `saved` card (`uses_holds = False`), or a hold
    released to go back to `scheduled` (`rescheduled`, `not_holdable`) whose cancel Stripe
    confirmed (until then `in_progress`: the authorization may still be live);
  - a failed deferred hold staff kept;
  - a charge an earlier call claimed and didn't finish, or that Stripe refused (below).
- Every other state answers `not_captured` and charges nothing, now and on every retry: a
  hold released outside `capture()` (by `release_for_charge`, whose caller charges; with its
  target; by staff), an authorization someone else cancelled in Stripe (released `lapsed`), a
  capture the card declined (`declined` first, then `not_captured`), a release Stripe refuses,
  a reused capture key, and an id with no hold row. The refusals that must survive a retry
  are recorded in `charge_blocked_reason` (`declined`, `lapsed`, `stale_charge`; on a hold
  captured in full, `target_cancelled`, see [Above the hold](#above-the-hold)); re-arming
  the target with a new card clears it. Decide these by hand: charge outside `capture()`, or
  cancel the target.
- The claim (`charge_key`, `charge_claimed_at`) is written in the same statement that settles
  the hold, before your charge runs, and `charged_at` once it returns, so a repeated
  `capture()` answers `charged` from the database.
- **A refused charge gets a new key.** Stripe saves the first answer for a key, errors
  included, and replays it for 24 hours; the same key with other parameters (another
  card) raises `IdempotencyError`. So when your `charge` raises a definite refusal (a
  `CardError`, or an `InvalidRequestError` other than a 409), nothing was taken:
  `capture()` answers `declined` (with `error`), drops the claim and bumps
  `charge_generation`, and the next call (once the customer has added another card, say)
  charges with `{prefix}-charge-{hold id}-{n+1}`. This applies to every charge, with or
  without a hold. That next call re-checks the target first, under its lock: a target
  cancelled (or deleted) since answers `not_captured` and charges nothing.
- **No answer keeps the key.** A charge that raised anything else (a connection error, a
  5xx, a 429, a 409, a bad or revoked key, `IdempotencyError`), or a process that died
  mid-charge, may have charged: the next call runs it again with the same key, which
  Stripe replays. **Stripe keeps an idempotency key for 24 hours only.** Such a charge
  claimed more than 23 hours ago is not re-run (Stripe may have forgotten the key and
  would charge again): it answers `not_captured`, logs an error, and is blocked
  (`stale_charge`). Check the charge in Stripe and settle it by hand. Retry a raised
  charge within the day.
- **Retry `capture()` until it answers a final result.** A call that raised, or answered
  `in_progress`, has not settled the target: call it again (from a task with backoff,
  say) until it answers `captured`, `paid`, `partially_paid`, `charged`, `declined`,
  `nothing_due` or `not_captured`. The sweep only finishes a difference left due above a
  captured hold (see [Above the hold](#above-the-hold)); nothing else is re-driven for you.
- **Keep asking for the same amount.** A capture that got no answer may still have run.
  Each call records the amount it asked for (`requested_amount_cents`) and that a capture
  was sent (`capture_sent_at`) before Stripe is called, and a capture recorded later (the
  webhook) is `paid` only when Stripe's amount is that one (or the hold plus the
  difference planned on top). Another amount stays `unpaid` and is logged as an error:
  settle it by hand.

| Result | When | Payments | `payment_status` |
|---|---|---|---|
| `captured` | The amount is within a live hold (`0 < amount <= held`): captured from it; Stripe releases the rest. | 1 (the hold) | `paid` |
| `paid` | Above a live hold: the whole hold captured, then the difference charged off-session. | 2 (hold + difference) | `paid` |
| `partially_paid` | Above a live hold, the hold captured, the card refused the difference. | 1 (the hold) | `partially_paid` |
| `charged` | No live hold to capture (expired, lapsed, scheduled, a saved card, a kept failed hold): your `charge` ran once, for the full amount. | 1 (your charge) | `paid` |
| `declined` | The card refused the capture, or your `charge` (a new key next time). | 0 | unchanged |
| `nothing_due` | Asked for 0: the hold is released. | 0 | `paid` (nothing is owed) |
| `in_progress` | Another call holds the claim, a placement or cancel is under way, or the difference is `processing`: retry. | – | unchanged |
| `not_captured` | Nothing taken, and a retry won't take anything either: decide by hand. | 0 | unchanged |

`captured` and `charged` keep their meanings from before; `paid` and `partially_paid` are
new, and only an amount above a live hold answers them (that used to answer `charged`,
after releasing the hold).

### Above the hold

A final amount above an authorized, unexpired hold (`expires_at` in the future) is taken
in two payments, both on the hold's row, so both belong to the same target:

1. **The hold, in full.** The amount above it is planned on the row
   (`difference_amount_cents`) before Stripe is called, then the whole hold is captured
   (`amount_to_capture` = the amount held), with the hold's capture key. Capturing first
   means a refused difference never costs the held amount. A capture the card declines,
   or a lapsed authorization, ends as on the [capture path](#capturing-on-the-date): a
   decline charges nothing, a lapsed authorization is charged the full amount through your
   `charge`.
2. **The difference.** Claimed in a conditional UPDATE, committed before the call
   (`difference_key` = `{prefix}-difference-{hold id}-{n}`, `difference_claimed_at`), then
   charged by the module itself: an automatic-capture PaymentIntent, off-session and
   confirmed, on the hold's saved card and customer, with
   `metadata = {card_hold_id, kind: "difference", difference_key}`. Succeeded: recorded
   (`difference_payment_intent_id`, `difference_charged_at`, its fee), `paid`.

The module charges the difference itself, not through your `charge`, because it already
has the card and the customer, and because its metadata lets the webhook and the lookup
recognise it as this hold's payment (never a stray authorization to cancel) and read its
fee.

Retries never charge twice:

- **Retried after the hold was captured** (the process died, or the difference got no
  answer): the capture is never sent again (the row reads `captured`); the difference is
  claimed (or its claim resumed with the same key, so Stripe replays it).
- **Not retried at all.** The sweep queues `charge_card_hold_difference` for a hold
  captured in full whose difference is still due and was never refused (`unpaid`), when
  no capture or difference claim on it is live (10 minutes) and the amount the last call
  asked is the hold plus the difference. It runs the same claimed, keyed path as
  `capture()`, and claims the difference in the same transaction that checks the target
  under its lock: a cancelled (or deleted) target is not charged, the row is marked
  (`charge_blocked_reason = target_cancelled`) so the sweep stops queuing it, and an
  error is logged once for someone to decide. A `capture()` for the same amount still
  charges it, and a refused one can still be marked paid outside.
- **Captured, but the amount unknown** (Stripe couldn't be read when the capture was
  recorded): the hold waits, never `paid` while an amount was asked for. The next
  webhook carrying the amount fills it in, or the sweep queues `record_card_hold_capture`
  (once no capture claim is live, 10 minutes), which reads it from Stripe; the hold is
  then settled as usual.
- **Asked for less after a capture got no answer.** A capture of the whole hold that got
  no answer may have run, so a later call within the hold keeps the planned difference
  (it is dropped only if no capture was ever sent). Its capture reuses the key, which
  Stripe refuses for another amount (`not_captured`); when the first capture's answer
  comes (the webhook), the hold is recorded `captured` but stays `unpaid`, with an
  error logged: it was captured for more than the last call asked. Settle it by hand.
- **Asked for less after the webhook recorded the capture.** A later call for another
  amount than the hold plus the difference records that ask (`requested_amount_cents`,
  while the difference is neither claimed nor charged), so no retry or sweep charges the
  old difference. Asked for exactly the amount captured, nothing more is due: the plan
  is dropped and the target is `paid` (`captured`). Asked for less, the customer was
  charged more than asked: `not_captured`, `unpaid`, an error logged. Refund it by hand.
- **No answer** (a connection error, a 5xx, a 429, a 409, a bad key, `IdempotencyError`)
  propagates and keeps the claim and its key. Past `CHARGE_KEY_TTL` (23 hours) it is never
  replayed: the difference's PaymentIntents are looked up in Stripe with the module's own
  Search on `metadata['difference_key']` (the customer's PaymentIntents listed when
  Search refuses; never `BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP`) and recorded; with none
  found, the key is rotated and it is charged afresh.
- **`processing`** (a bank debit still settling): `in_progress`, and the PaymentIntent is
  kept (`difference_payment_intent_id`); the next call reads it back from Stripe instead
  of sending the create again, and the webhook records the outcome.
- **Refused** (a `CardError`, a non-409 `InvalidRequestError`, or a PaymentIntent left
  needing a payment method): `partially_paid`. The held amount stays taken; the claim is
  dropped and `difference_generation` bumped, `difference_failure_code` records the
  bank's code, and `difference_charge_failed` is sent. A later `capture()` for the same
  amount (once the customer fixed their card, say) charges it again with the next key;
  its target is re-checked first under its lock, and a cancelled one is not charged. The
  module never retries a refused difference on its own.
- **Paid outside the app.** `mark_paid_outside(hold_id, actor)` moves a `partially_paid`
  hold to `paid` (`paid_outside_at`, `paid_outside_by`) in one conditional UPDATE,
  refused while a capture holds the claim; no later `capture()` charges the difference.
  Staff can do it through GraphQL: `cardHoldMarkPaid(input: {id})`, gated by
  `change_cardhold` like `cardHoldKeep` / `cardHoldCancel`.

A webhook for the difference (`payment_intent.succeeded`, `payment_intent.payment_failed`)
records it the same way, under the target's lock and then the hold's, only for the
outstanding key; one for an old key is ignored, and the difference is never cancelled.

### Payment status and signals

Every hold has a `payment_status` (`CardHold.PaymentStatus`), exposed in GraphQL as
`CardHold.paymentStatus` to whoever can read the hold:

| Value | Meaning |
|---|---|
| `unpaid` | Nothing taken yet. |
| `paid` | The final amount was taken: captured within the hold, the hold plus the difference, a single full charge (with or without a hold), or the rest marked paid outside. Also a `capture()` of 0 once the hold is released (`nothing_due`): nothing is owed. |
| `partially_paid` | **Only** when the hold was captured in full and the difference above it was refused. |

Signals, from `baseapp_payments.signals`, each sent once per change, after the commit:

- `payment_status_changed` (`hold`, `target`, `previous`, `payment_status`): mirror the
  status onto your own record here.
- `difference_charge_failed` (`hold`, `target`, `amount_due_cents`, `error_code`): the
  difference was refused; notify the customer and staff, and collect the rest (a payment
  link, another card, by hand). Out of scope for the module.

```python
from django.dispatch import receiver

from baseapp_payments.signals import difference_charge_failed, payment_status_changed


@receiver(payment_status_changed)
def mirror_payment_status(sender, hold, target, payment_status, **kwargs):
    type(target).objects.filter(pk=target.pk).update(payment_status=payment_status)


@receiver(difference_charge_failed)
def ask_for_the_rest(sender, hold, target, amount_due_cents, error_code, **kwargs):
    notify_difference_due(target, amount_due_cents, error_code)
```

### One invoice for every payment

When you raise a Stripe invoice for the target, record its payments on it with
`attach_payments_to_invoice(hold_id, invoice_id)`. It attaches every PaymentIntent that
took money for the target (`hold_payment_intent_ids(hold)`: the hold's capture, the
difference, or the single full charge) with `stripe.Invoice.attach_payment(invoice,
payment_intent=...)` (basil, stripe-python 12.2+), skipping any already on the invoice
(every page of `stripe.InvoicePayment.list(invoice=...)`; the invoice's own `payments`
holds only the first few), each with its own idempotency key. Stripe credits a succeeded
PaymentIntent at once; the invoice turns `paid` when `amount_remaining` reaches 0.

The invoice must be for the hold's customer and currency, finalized (`open`), and its
total must cover the payments. Create it so Stripe doesn't try to collect it itself:

```python
invoice = stripe.Invoice.create(
    customer=hold.stripe_customer_id,
    collection_method="send_invoice",
    days_until_due=1,
    auto_advance=False,
)
stripe.InvoiceItem.create(
    customer=hold.stripe_customer_id, invoice=invoice.id, amount=final_cents, currency="usd"
)
stripe.Invoice.finalize_invoice(invoice.id, auto_advance=False)
attach_payments_to_invoice(hold.pk, invoice.id)
```

Call it outside a transaction (`CardHoldInTransaction` otherwise); Stripe's errors
propagate.

### Fees

Stripe's actual fee is stored per payment, from the charge's balance transaction
(`latest_charge.balance_transaction.fee`, expanded on the capture and the difference):
`capture_fee_cents`, `difference_fee_cents`, `charge_fee_cents`, in `fee_currency` (your
account's settlement currency). When Stripe hasn't made the balance transaction yet, the
fee is left empty and the sweep queues `record_card_hold_fees` for it (payments from the
last 3 days), which reads it later. `CardHold.objects.with_payment_totals()` annotates
`paid_cents` (every payment) and `fees_cents` (their fees), for your totals and margins.

`release_for_charge(hold_id)` is for when you charge the final amount yourself: it releases the
hold under the same claim and returns `True` only when the hold is released for your charge
(by this call or an earlier one), never for one `capture()` charged, declined or found
cancelled by someone else. A hold released to go back to `scheduled` (`rescheduled`,
`not_holdable`) is released for your charge once Stripe confirmed its cancel (`False` until
then). After a charge `capture()` declined it answers `False`: `capture()` charges that one
again. It raises `CardHoldInTransaction` inside a transaction too.

### Holds placed later (the window)

Off by default, and only for adapters with `uses_holds = True`. A Visa authorization placed
without the customer present lasts 5 days (Stripe's exact window is 4 days 18 hours), so a
target dated further out can't be held at checkout. With deferral on, it is held
`window_days` before its date instead (`CARD_HOLDS_WINDOW_DAYS`, default 4, clamped to 1–4,
also for an adapter's own `window_days()`).

**The capture deadline.** The sweep places a due hold at its first run of the `hold_on` day,
D−4 at about 00:15 with the default window. 4 days 18 hours later is about 18:00 on D: capture
before then, or the authorization lapses and `capture()` charges afresh. The real expiry is
always read from `capture_before` (`expires_at`), which is what `capture()` relies on; a
shorter window only moves the deadline later.

> **Not checked against Stripe test mode yet:** the 4 days 18 hours of an off-session
> authorization comes from Stripe's documentation, and Stripe classifies an authorization as
> merchant- or customer-initiated from its signals. Check the `capture_before` your account
> returns before relying on the window.

**Turning it on.** Set `CARD_HOLDS_DEFERRAL_ENABLED = True` in Constance, give your
adapter a `target_date(target)` and a `cancel(target, actor)`, make sure your customer
terms cover off-session holds (see the box above), and handle the new results in your
create mutation:

```python
from baseapp_payments.holds import complete_setup_on_session

if input.get("setup_intent_id"):
    result = complete_setup_on_session(input["setup_intent_id"], link, **common)
elif input.get("payment_intent_id"):
    result = complete_on_session(input["payment_intent_id"], link, **common)
else:
    result = authorize_on_session(...)
payload = card_hold_payload(result)
if result.status not in (
    PlacementStatus.PLACED,
    PlacementStatus.SCHEDULED,
    PlacementStatus.CARD_SAVED,
    PlacementStatus.REQUIRES_ACTION,
):
    return cls(errors=errors_for(result), **payload)
return cls(order=result.target, **payload)
```

Call `reschedule_on_commit(target)` from every path that changes a target's date (see
below). Turning deferral off again stops every new off-session placement: no new deferrals,
no placing of scheduled holds (the sweep, a queued `place_card_hold`, a card saved whose day
has come), no rescheduling (`reschedule_hold`, also a task queued before). Scheduled holds left
then close like a target without a hold (`capture` charges afresh). A hold released
`rescheduled` or `not_holdable` still goes back to `scheduled` once Stripe confirms its cancel
(the sweep queues it either way), and then waits there like the others. Releases of scheduled
holds keep working either way, and so does settling a placement already sent to Stripe that
got no usable answer (`placement_key`), as stopping it could strand an authorization Stripe
made: it is replayed with its key for 23 hours after it was first sent, then reconciled
(see [Lost answers and reconciliation](#lost-answers-and-reconciliation)).

**Statuses.**

| Status | Meaning |
|---|---|
| `scheduled` | The card is saved; nothing is authorized until `hold_on`. The card is in use. |
| `saved` | `uses_holds = False`: the card is saved and nothing is ever authorized; `capture()` charges it on the date. |
| `authorized` | Placed (on-session, or off-session by the sweep). |
| `failed` | The off-session placement was refused. Final: never retried, never re-armed. |
| `failed` + `kept_at` | Staff kept the target: it closes by a fresh charge. Final. |
| `released` (`cancelled`, with `failed_at`) | Staff cancelled the target of a failed hold. |
| `released` (`rescheduled`) | Briefly, while a placed hold moves back to `scheduled`. |
| `released` (`not_holdable`) | Briefly, while an authorization placed for a target outside `filter_holdable` is cancelled; then back to `scheduled`. |

**Placing at checkout.** `authorize_on_session` checks the target's date first: no date,
or one within the window, holds now, on-session, as before. Further out, it authorizes
nothing: it saves the card with an off-session SetupIntent (key
`{prefix}-setup-{user}-{attempt}`) and links the hold `scheduled`, with `hold_on` = date −
window, answering `scheduled`. If the bank wants the customer to authenticate the saved
card, the answer is `requires_action` with `intentType` `setup_intent`; the second pass is
`complete_setup_on_session(setup_intent_id, ...)`, with the same rules as
`complete_on_session`. A hold whose day has already come when it is linked is placed at
once. An existing target's `released` hold is re-armed `scheduled` on the same row.

**Placing ahead of the date.** The sweep queues `place_card_hold` for every scheduled hold
whose `hold_on` has come and whose target is still in `filter_holdable` (and not
cancelled). `place_scheduled(hold_id)` claims the row under the target's lock and then the
hold's (the claim commits before Stripe is called, so overlapping sweeps or a redelivered
task answer `in_progress` and call nothing), re-checks the target (cancelled or done with
the card: released with no Stripe call), prices it now, and creates one off-session,
manual-capture PaymentIntent (`off_session=True`, `confirm=True`) for the current hold
amount, with the key `{prefix}-hold-scheduled-{hold}-{attempt}-{n}` (`n`: how many
authorizations the row held before). Success: `authorized`, expiry from `capture_before`,
`card_hold_authorized`.

**A failed hold is final.** A decline (the bank's `decline_code` when it sends one),
`authentication_required`, or any non-retryable Stripe error marks the hold `failed` with
`failure_code` (GraphQL `failureReason`), sends `card_hold_failed` (`hold`, `target`) and
calls your adapter's `notify_hold_failed(target, hold)`, after the commit. The default
emails `staff_recipients(target)` with Django mail, one email per language: the customer,
the target, its date and the reason. Override it to notify some other way. The customer
isn't told (their GraphQL reads `failed` as `scheduled`), and it is never retried. No
usable answer isn't a failure: a connection error, a 5xx, a 429, a 409, and a bad or revoked
API key (`AuthenticationError`, `PermissionError`, logged as an error so someone fixes it).
The hold stays `scheduled` with its key and amount, no one is emailed, and the next sweep
retries with the same key, so Stripe replays any authorization it made; the webhook usually
records it first. Stripe saves a 5xx for its key and replays it, so a hold behind one stays
scheduled; but only for 23 hours after the key was first sent (`placement_sent_at`, kept
across replays): past that Stripe may have forgotten the key and a replay could authorize
twice, so the sweep reconciles it instead (below).
A placement that settles after its target was cancelled releases what it authorized and
tells nobody. One whose target is only outside `filter_holdable` is released
`not_holdable`, with that PaymentIntent, until Stripe confirms the cancel (the sweep
re-drives it, and `capture()` answers `in_progress` meanwhile); then the sweep moves it back
to `scheduled`, deferral on or off. One whose target was deleted while its placement was unsettled is replayed by
the sweep with the same key and amount (reconciled past 23 hours), and whatever comes back
is cancelled.

**Staff decide a failed hold.** `keep_failed_hold(hold_id, actor)` sets `kept_at` /
`kept_by`: when the target closes, `capture()` charges afresh through your `charge`, once.
Until staff decide, `capture()` of a failed hold answers `not_captured` and charges
nothing. `cancel_failed_hold(hold_id, actor)` calls your adapter's `cancel(target, actor)`
under the locks and releases the hold (`cancelled`); nothing is charged. Both refuse
(`False`) a hold that isn't `failed`, or is already kept; `cancel_failed_hold` also
refuses (and logs an error for) a hold whose target model is no longer registered. GraphQL: `cardHoldKeep(input:
{id})` and `cardHoldCancel(input: {id})`, registered by the plugin. They need
`change_cardhold` on the hold, which `PaymentsPermissionsBackend` answers from the
model-level grant only: the hold's customer never has it, and staff status alone isn't
enough.

**The date changes.** Card holds don't watch your date field: call
`reschedule_on_commit(target)` from the path that changes it (it queues the
`reschedule_card_hold` task once your change commits), or `reschedule(target)` outside a
transaction. A placed hold whose new date is outside the window, or still inside it but
after the authorization expires (`expires_at` before the new date begins), is released
(`rescheduled`; Stripe is asked to cancel it) and the same row goes back to `scheduled`
with its new `hold_on`, placed off-session at once when that day has come. A scheduled hold gets its new `hold_on`; one now inside the window
is placed off-session at once, by the same path as the sweep. Failed and kept holds are
left alone. While a capture or a placement is under way it answers `in_progress`, and the
task retries (up to 12 times, backoff capped at 1500 s); the sweep finishes a hold left
released `rescheduled`.

**Cancelling before placement.** Releasing a scheduled hold or a saved card (`release_target_holds_on_commit`,
deleting the target, the sweep, `release_for_charge`, or `capture()` charging instead)
makes no Stripe call: it is marked released and confirmed, nothing is charged, and its
card is no longer in use once the target is cancelled. A scheduled hold whose placement is
under way is left to the placement, which settles it.

### Background work

- `baseapp_payments.tasks.release_card_hold`: cancels one hold's PaymentIntent.
- `baseapp_payments.tasks.sweep_card_holds`: beat entry
  `baseapp_payments_card_holds_sweep`, every 15 minutes (expires after 15). It releases holds
  with no target 30 minutes after creation, re-drives released holds whose cancel Stripe
  hasn't confirmed, releases holds on cancelled targets, and holds on targets done with the
  card unless a charge may be in flight. It also queues `place_card_hold` for every scheduled
  hold whose placement got no usable answer, deferral on or off, including one whose target
  was deleted since, so Stripe replays it (or, past 23 hours, it is reconciled) and whatever
  it authorized for a deleted target is cancelled. It re-drives the cancel of stray
  authorizations (`stray_payment_intent_ids`) until Stripe confirms it, and queues
  `reconcile_card_hold` for an on-session row whose create got no usable answer 23 hours
  ago; such a row is never released as an orphan. It queues `reschedule_card_hold` for a hold
  released `rescheduled` or `not_holdable` whose cancel Stripe confirmed, deferral on or off. The entry is registered for every project (plugin
  settings are built before your settings can be read); without a card hold model the task
  returns before any query. It skips a hold a release task stamped in the last
  30 minutes (`release_requested_at`), so waiting retries aren't duplicated, and a broker
  error on one hold doesn't stop the rest.

- `baseapp_payments.tasks.place_card_hold`: places one due scheduled hold off-session (a no-op
  with deferral off, unless it settles a placement already sent).
- `baseapp_payments.tasks.reschedule_card_hold`: follows one hold's change of date (a no-op with
  deferral off), and puts a hold released `rescheduled` or `not_holdable` back to `scheduled`
  (deferral on or off; with it off the row isn't placed then).
- `baseapp_payments.tasks.charge_card_hold_difference`: charges the difference still due
  above a hold captured in full whose `capture()` stopped coming back
  (`holds.charge_due_difference`; queued by the sweep, which queues it again after a
  Stripe error).
- `baseapp_payments.tasks.record_card_hold_fees`: reads Stripe's fee for a payment whose
  balance transaction wasn't ready when it was taken (queued by the sweep).
- `baseapp_payments.tasks.reconcile_card_hold`: records what one PaymentIntent naming a hold
  is now (queued by the webhook), or closes a stale on-session create (queued by the sweep).
  Retries Stripe's transient errors up to 12 times.

### Lost answers and reconciliation

A create that gets no usable answer (a 5xx, a connection error) may hide an authorization
Stripe made. Stripe's guidance: treat a 5xx as indeterminate; retry with the same key and
parameters only within 24 hours (Stripe prunes keys after at least 24 hours, and a later
"replay" runs as a fresh request: a second authorization); after that, don't retry with the
old key or a new one until reconciled, from the objects and webhook events. Card holds do
exactly that.

**A local id in the metadata.** Every authorization card holds create names its row in
`metadata['card_hold_id']`: the off-session placement (the scheduled hold), and the
on-session first pass, whose `pending` row is written before the create for this reason.
(A SetupIntent authorizes nothing and isn't reconciled.)

**Webhooks (primary).** Subscribe the endpoint to:

| Event | What it records |
|---|---|
| `payment_intent.amount_capturable_updated` | An authorization. The answer of the hold's placement in flight (its key unsettled, the same amount) is recorded as the placement would record it: `authorized`, or released `not_holdable` / for a cancelled target as usual. An on-session create's is recorded on its row, and the client's retry carries on with it. Any other authorization naming the hold (an old key's orphan, one made after a key was pruned) is a *stray*: cancelled. |
| `payment_intent.canceled` | Confirms a release that waited for Stripe (`release_confirmed_at`), or a stray's cancel. |
| `payment_intent.succeeded` | The hold's own PaymentIntent was captured: recorded through `mark_captured` (`paid`, unless a difference is still due). The outstanding difference (`kind` `difference`) succeeded: recorded, `paid`. |
| `payment_intent.payment_failed` | The decline of the outstanding placement: the hold fails as it would have (`failed`, staff told). The decline of the outstanding difference: `partially_paid`, `difference_charge_failed`. Any other is ignored. |

The webhook itself reads and writes nothing: it queues `reconcile_card_hold` (answering 500
if the broker refuses, so Stripe redelivers) and answers 2xx at once. The task reads the
PaymentIntent live from Stripe and records that, under the target's lock and then the
hold's, so events that come twice, out of order, or before the placement's own answer is
recorded settle the same way. Stripe also sends events for objects it created during an
incident, but doesn't guarantee to, hence the lookup.

**Strays** are recorded on the hold (`stray_payment_intent_ids`) and cancelled through the
release task after the commit; so is the PaymentIntent of an off-session placement whose
answer arrives after a webhook or lookup already settled the hold with another; the sweep re-drives each cancel until Stripe confirms it.

**The 23-hour lookup (backup).** `placement_sent_at` records when a key was first sent;
replays never move it. Once it is older than `PLACEMENT_KEY_TTL` (23 hours, next to
`CHARGE_KEY_TTL`), the create is never replayed again:

- a scheduled hold's placement (`place_card_hold`, from the sweep) looks its PaymentIntents
  up in Stripe and records them as the webhook would. With none found, its key is rotated
  (`placement_generation`, a new suffix on `{prefix}-hold-scheduled-...`), the claim
  cleared, and the next sweep places it afresh;
- an on-session row answers `in_progress` until the sweep's `reconcile_card_hold` looks it
  up: the row is closed (`released`, `abandoned`), whatever was found is cancelled as a
  stray, and the attempt answers `declined`, so the client starts a new one.

The lookup is `holds.find_hold_payment_intents(hold)`: Stripe's Search,
`metadata['card_hold_id']:'<id>'`. **Search lags** up to about a minute behind writes
(harmless 23 hours later), and **isn't available in every region** (India, for one): when it
raises anything but a transient error, the customer's PaymentIntents created since an hour
before the first send are listed (`PaymentIntent.list(customer=..., created={"gte": ...})`)
and filtered by the metadata. Set `BASEAPP_PAYMENTS_CARD_HOLD_LOOKUP` to a dotted path of
your own function of the hold to replace it. **It must return every PaymentIntent whose
metadata carries the hold's `card_hold_id`, in any status and of any kind**: manual-capture
authorizations, captured or cancelled ones, and automatic-capture payments such as the
difference above the hold. One that leaves some out lets a lost authorization slip by
uncancelled, or a placement be sent again. (The difference itself is never looked up
through it: past 23 hours it is found with the module's own Search on
`metadata['difference_key']`, so an override can never get it charged twice.)

Signals `card_hold_authorized` (`hold`, `target`), `card_hold_released` (`hold_id`),
`card_hold_failed` (`hold`, `target`), `payment_status_changed` and
`difference_charge_failed` (see [Payment status and signals](#payment-status-and-signals))
are sent from `baseapp_payments.signals` after the change commits.

### GraphQL

GraphQL is optional (the `graphql` extra). With it installed and card holds enabled:

- `CardHold` (`CardHoldObjectType`, swappable through `CardHold.get_graphql_object_type()`):
  `status`, `amountCents`, `estimatedAmountCents`, `expiresAt`, `brand`, `last4`, `holdOn`,
  `kept`, `failureReason`, `paymentStatus`. Only the hold's customer (while active), and users granted the
  model's `view_cardhold` permission (staff status alone is not enough), can read it, including
  through `node(id:)` and `cardHold`. Anyone without `view_cardhold` on the model (the
  customer, even a staff one) sees a `failed` hold as `scheduled`, `kept` as false and
  `failureReason` as null. `status` reads `saved` for a card saved without a hold.
- `CardHoldsInterface` adds `cardHold` to your target's ObjectType:
  `interfaces = graphql_shared_interfaces.get(RelayNode, "CardHoldsInterface")`. The field
  carries its own optimizer hook (it prefetches `document__card_hold`), so a page of
  targets costs the same queries however many rows it has, `holdOn` included (the hold's
  own stored `hold_on`, the day the sweep uses); consumers wire up nothing.
- `cardHoldKeep` / `cardHoldCancel`: staff decisions on a failed deferred hold (above).
- `cardHoldMarkPaid`: staff record a `partially_paid` target as paid outside the app
  (above); `change_cardhold` too, and `invalid_action` for any other hold.
- `CardHoldPaymentInputMixin` (`paymentMethodId`, `attemptId`, `paymentIntentId`,
  `setupIntentId`) and `CardHoldPayloadMixin` (`requiresAction`, `clientSecret`, `intentType`,
  `holdStatus`, `holdOn`) for your own create mutation. There is no REST surface for holds.

### Admin

`CardHoldAdmin` is registered read-only; it lists `hold_on`, whether staff kept a failed
hold, and the failure code, and filters by status and release reason. For your target's admin,
`card_hold_admin_summary(target)` returns a line such as
`Visa 4242 · 110.00 USD held · Authorized · expires 2030-03-17 12:00 UTC` (in the hold's own
currency). It costs one query per call; in a `list_display` column, prefetch the holds in your
admin's `get_queryset` (`.prefetch_related(CARD_HOLD_PREFETCH_PATH)`, from
`baseapp_payments.models`) and it costs none.

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).

### Stripe test-mode QA

`testproject/testapp/management/commands/card_holds_stripe_qa.py` runs the payments flows
end to end against Stripe **test mode** and prints a pass/fail table: saving a card; a
subscription created and renewed on a test clock (reading basil's item-level period); a
hold captured within it; a capture above the hold (`paid`, two payments, one invoice,
fees stored); a declined difference (`partially_paid`, `difference_charge_failed`); marking
it paid outside (`paid`); and an expired hold closed by one full charge. It refuses to run
unless `STRIPE_SECRET_KEY` starts with `sk_test_` or `rk_test_`, and never prints the key.

```bash
# STRIPE_SECRET_KEY=sk_test_... in .env, then:
docker compose exec -T web uv run --python 3.12 python manage.py card_holds_stripe_qa
```

Stripe has no test card that authorizes once and declines later, so the declined
difference attaches `pm_card_chargeCustomerFail` ("attach succeeds, charges fail",
4000 0000 0000 0341) and points the placed hold at it before capturing. The run creates
test customers, a product, a price and a test clock in your Stripe test account and rows
in your database; it cleans nothing up, so use a scratch database. Its unit test
(`testproject/testapp/tests/test_card_holds_stripe_qa.py`) only checks the guard and the
table; it never calls Stripe.

### Prerequisites when activating `baseapp_payments`

Because the models are abstract + swappable with no concrete models shipped, create a local app (we suggest `apps/payments/`) implementing the concrete models — note the required `FieldTracker` on `Customer`:

```python
from model_utils import FieldTracker

from baseapp_payments.models import BaseCustomer, BaseSubscription


class Customer(BaseCustomer):
    tracker = FieldTracker(["entity"])

    class Meta(BaseCustomer.Meta):
        pass


class Subscription(BaseSubscription):
    class Meta(BaseSubscription.Meta):
        pass
```

Then point swapper at them and run `makemigrations` / `migrate`:

```python
BASEAPP_PAYMENTS_CUSTOMER_MODEL = "payments.Customer"
BASEAPP_PAYMENTS_SUBSCRIPTION_MODEL = "payments.Subscription"
```
