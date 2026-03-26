# Profile API Requirements

## Response contract

- `build_profile_response(user)` must return an object with `user_id`, `display_name`, and `email_verified`.
- The response contract must use the field name `display_name`; clients must not need to read a legacy `name` key.
- `email_verified` must always be present in the response, even when the value is `false`.
