---
layout: home

hero:
  name: API Drift Agent
  tagline: Detect breaking API changes in provider PRs. Automatically open GitHub Issues in affected consumer repos.
  actions:
    - theme: brand
      text: Get Started
      link: /guide
    - theme: alt
      text: View on GitHub
      link: https://github.com/DriftAgent/api-drift-agent
      target: _blank
    - theme: alt
      text: GitHub Marketplace
      link: https://github.com/marketplace/actions/api-drift-agent
      target: _blank

features:
  - title: Auto-detect schemas
    details: Automatically detects OpenAPI, GraphQL, and gRPC/Protobuf schemas — no configuration required in most projects.
  - title: Consumer issue tracking
    details: Opens, updates, and closes GitHub Issues in consumer repos as breaking changes are introduced or resolved.
  - title: Idempotent CI
    details: Fully re-run safe. Comments and issues are updated in-place — no duplicates across multiple CI runs.
---
