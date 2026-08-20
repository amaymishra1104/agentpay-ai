# Security Foundation

## Principles

- Store credentials in environment variables only.
- Keep Razorpay secret keys backend-only.
- Enforce least privilege between modules.
- Preserve auditability for critical actions.

## Current status

- `.env.example` files added at root, frontend, and backend.
- No real credentials included.
- Razorpay is configured for TEST MODE placeholders only.
