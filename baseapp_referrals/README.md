# BaseApp Referrals

Reusable app to track who referred whom. It provides a swappable `UserReferral` model (referrer → referee), reversible **referral-code** helpers (Hashids over the user PK), and a social-auth pipeline step to link a new user to their referrer at sign-up.

`baseapp_referrals` follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin so it participates in `INSTALLED_APPS` aggregation. It contributes no middleware, auth backends, GraphQL roots or URLs — the referral flow is consumed by `baseapp_auth` (the registration serializer) and an optional social-auth pipeline step.

## How to install

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

Referrals is **opt-in** (it ships commented out in the template's base settings).

1. Add `baseapp_referrals` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_referrals",
    # ...
]
```

2. Define the concrete `UserReferral` model (see [models](#models)) and point the swapper setting at it:

```python
BASEAPP_REFERRALS_USERREFERRAL_MODEL = "referrals.UserReferral"
```

Run `./manage.py makemigrations` / `./manage.py migrate` after defining it.

## Models

`BaseUserReferral` is abstract + swappable, and the package ships **no** concrete model or migrations — your project must subclass it and point the swapper setting at the concrete model (see [How to develop](#how-to-develop)).

| Abstract | Concrete reference | Purpose |
|---|---|---|
| `BaseUserReferral` | `UserReferral` | Links a `referrer` (FK, `user.referrals`) to a `referee` (OneToOne, `user.referred_by`). The one-to-one on `referee` enforces a user can be referred only once. |

## Referral codes

`baseapp_referrals.utils` encodes/decodes a user's referral code with Hashids (salt `"referral-codes"`, min length 4) — so codes are reversible, not stored:

```python
from baseapp_referrals.utils import get_referral_code, get_user_from_referral_code

code = get_referral_code(user)                 # e.g. "x9Qk" — derived from user.pk
referrer = get_user_from_referral_code(code)   # the User, or None if the code is invalid
```

## Linking referrals at sign-up

### Via the auth register serializer

`baseapp_auth`'s registration serializer accepts an optional `referral_code` field (validated through `get_user_from_referral_code`) and exposes the current user's own `referral_code` on the user serializer. With both packages installed, passing `referral_code` at registration resolves and records the referrer — no extra wiring needed.

### Via a social-auth pipeline (optional)

For social sign-up, `baseapp_referrals.pipeline.link_user_to_referrer` creates a `UserReferral` from a `referral_code` in the request data when the user is newly created. Add it to your `SOCIAL_AUTH_PIPELINE`:

```python
SOCIAL_AUTH_PIPELINE = (
    # ... standard social-auth steps ...
    "baseapp_referrals.pipeline.link_user_to_referrer",
)
```

The step is a no-op for existing users and when no `referral_code` is present.

## Admin

`UserReferral` is registered in the Django admin (`UserReferralAdmin`) listing `referrer` / `referee` for easy inspection.

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).

### Prerequisites when activating `baseapp_referrals`

Because the model is abstract + swappable with no concrete model shipped, create a local app (we suggest `apps/referrals/`) implementing the concrete model:

```python
from baseapp_referrals.models import BaseUserReferral


class UserReferral(BaseUserReferral):
    class Meta(BaseUserReferral.Meta):
        pass
```

Then point swapper at it and run `makemigrations` / `migrate`:

```python
BASEAPP_REFERRALS_USERREFERRAL_MODEL = "referrals.UserReferral"
```
