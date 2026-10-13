---
name: conflict-deploy-a
description: Deploy services with mandatory canary rollout. Use when deploying production services.
---

# Deploy policy A

- Always require canary deployment before production
- You must wait for metrics before full rollout
- Never skip canary for production services
