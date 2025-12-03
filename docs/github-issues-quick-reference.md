# GitHub Issues Quick Reference - Phase 1

This document provides a quick reference to all 12 Phase 1 GitHub issues for the Raspberry Pi MCP Server project. Each issue is designed for a 6-hour GitHub Copilot Agent session.

**Full Details**: See [github-copilot-agent-issue-plan.md](github-copilot-agent-issue-plan.md) for complete issue descriptions, acceptance criteria, and custom prompts.

---

## Issue Summary Table

| # | Title | Effort | Complexity | Dependencies | Hardware | Status |
|---|-------|--------|------------|--------------|----------|--------|
| 1 | Project Foundation & Configuration System | 5-6h | Medium | None | No | ⬜ |
| 2 | MCP Server Core & JSON-RPC Protocol | 5-6h | High | #1 | No | ⬜ |
| 3 | Privileged Agent & IPC Communication | 5-6h | Medium-High | #2 | No | ⬜ |
| 4 | Security Foundation - OAuth, RBAC & Audit Logging | 6h | High | #3 | No | ⬜ |
| 5 | System Information & Power Management Tools | 5-6h | Medium | #4 | No | ⬜ |
| 6 | GPIO & I2C Device Control | 5-6h | Medium | #4 | Yes | ⬜ |
| 7 | Service & Process Management Tools | 5-6h | Medium | #4 | No | ⬜ |
| 8 | Metrics Sampling & Query System | 5-6h | Medium | #4 | No | ⬜ |
| 9 | Logging Tools & Camera Support | 5-6h | Medium | #4 | Camera (optional) | ⬜ |
| 10 | Self-Update Mechanism - Part 1 (Foundation) | 6h | High | #4 | No | ⬜ |
| 11 | Self-Update Mechanism - Part 2 (State Machine) | 6h | Very High | #10 | No | ⬜ |
| 12 | Deployment & Final Integration | 5-6h | Medium | #1-11 | No | ⬜ |

**Total Estimated Time**: 96 hours (16 x 6-hour sessions)
**Expected Duration**: ~6 weeks (2 issues per week)

---

## Issue Titles (Copy-Paste Ready)

### Critical Path (Sequential - Weeks 1-2)
```
[Phase 1] Project Foundation & Configuration System
[Phase 1] MCP Server Core & JSON-RPC Protocol
[Phase 1] Privileged Agent & IPC Communication
[Phase 1] Security Foundation - OAuth, RBAC & Audit Logging
```

### Tools & Features (Can be done in any order after #4 - Weeks 3-4)
```
[Phase 1] System Information & Power Management Tools
[Phase 1] GPIO & I2C Device Control
[Phase 1] Service & Process Management Tools
[Phase 1] Metrics Sampling & Query System
[Phase 1] Logging Tools & Camera Support
```

### Self-Update & Deployment (Sequential - Weeks 5-6)
```
[Phase 1] Self-Update Mechanism - Part 1 (Foundation)
[Phase 1] Self-Update Mechanism - Part 2 (State Machine)
[Phase 1] Deployment & Final Integration
```

---

## Dependency Graph

```
Issue #1 (Foundation)
    ↓
Issue #2 (MCP Server)
    ↓
Issue #3 (IPC)
    ↓
Issue #4 (Security)
    ↓
    ├──→ Issue #5 (System Tools)
    ├──→ Issue #6 (GPIO/I2C) [Hardware Required]
    ├──→ Issue #7 (Services)
    ├──→ Issue #8 (Metrics)
    ├──→ Issue #9 (Logs/Camera)
    └──→ Issue #10 (Update Part 1)
            ↓
         Issue #11 (Update Part 2)
            ↓
         Issue #12 (Deployment)
```

**Parallel Opportunities**: After Issue #4, Issues #5-9 can be worked in parallel or any order.

---

## Implementation Sequence Recommendations

### Week 1: Foundation (Issues #1-2)
- **Monday-Wednesday**: Issue #1 - Project Foundation (6h)
- **Thursday-Saturday**: Issue #2 - MCP Server Core (6h)
- **Outcome**: Basic project structure, config system, JSON-RPC server skeleton

### Week 2: IPC & Security (Issues #3-4)
- **Monday-Wednesday**: Issue #3 - Privileged Agent & IPC (6h)
- **Thursday-Saturday**: Issue #4 - Security Foundation (6h)
- **Outcome**: Working IPC, OAuth, RBAC, audit logging

### Week 3: System & Device Tools (Issues #5-6)
- **Monday-Wednesday**: Issue #5 - System Information (6h)
- **Thursday-Saturday**: Issue #6 - GPIO & I2C (6h) [Need hardware for testing]
- **Outcome**: System monitoring, power management, GPIO/I2C control

### Week 4: Services & Metrics (Issues #7-8)
- **Monday-Wednesday**: Issue #7 - Service Management (6h)
- **Thursday-Saturday**: Issue #8 - Metrics System (6h)
- **Outcome**: Service control, process monitoring, time-series metrics

### Week 5: Logging & Updates Part 1 (Issues #9-10)
- **Monday-Wednesday**: Issue #9 - Logging & Camera (6h)
- **Thursday-Saturday**: Issue #10 - Self-Update Foundation (6h)
- **Outcome**: Log querying, camera capture, version management

### Week 6: Updates Part 2 & Deployment (Issues #11-12)
- **Monday-Thursday**: Issue #11 - Self-Update State Machine (6h)
- **Friday-Saturday**: Issue #12 - Deployment (6h)
- **Outcome**: Complete self-update with rollback, systemd integration, release-ready

---

## GitHub Labels to Create

Create these labels in your repository for issue tracking:

| Label | Color | Description |
|-------|-------|-------------|
| `copilot-agent` | `#0052CC` | Assigned to GitHub Copilot Agent |
| `phase-1` | `#0E8A16` | Phase 1 implementation |
| `effort-6h` | `#FBCA04` | Estimated 6 hours of work |
| `effort-5h` | `#FEF2C0` | Estimated 5 hours of work |
| `complexity-low` | `#C2E0C6` | Low complexity |
| `complexity-medium` | `#FFE97F` | Medium complexity |
| `complexity-high` | `#FF9966` | High complexity |
| `complexity-very-high` | `#D93F0B` | Very high complexity |
| `hardware-required` | `#5319E7` | Requires hardware for testing |
| `critical-path` | `#B60205` | Blocking other issues |

---

## Creating Issues - Checklist

For each issue:

- [ ] Create GitHub issue with title from this document
- [ ] Copy issue description from [github-copilot-agent-issue-plan.md](github-copilot-agent-issue-plan.md)
- [ ] Add appropriate labels (copilot-agent, phase-1, effort, complexity)
- [ ] Link dependency issues (if any) using "depends on #N"
- [ ] Assign to GitHub Copilot Agent
- [ ] Paste custom prompt in Copilot Agent prompt field
- [ ] Monitor progress and review when complete

---

## Progress Tracking

Update the status column in the table above:
- ⬜ Not started
- 🟦 In progress (Copilot Agent working)
- 🟨 Review needed (human review required)
- ✅ Complete (merged to main)
- 🚫 Blocked (waiting on dependency)

**Current Phase**: Issue #__ of 12
**Completion**: __% (__ of 12 issues complete)
**Estimated Completion Date**: [Calculate based on 2 issues/week]

---

## References

- **Detailed Issue Specifications**: [github-copilot-agent-issue-plan.md](github-copilot-agent-issue-plan.md)
- **Phase 1 Scope Matrix**: [phase-1-scope-matrix.md](phase-1-scope-matrix.md)
- **Acceptance Checklist**: [acceptance-checklist.md](acceptance-checklist.md)
- **Issue Template**: [../.github/ISSUE_TEMPLATE/copilot-agent-implementation.md](../.github/ISSUE_TEMPLATE/copilot-agent-implementation.md)

---

**Document Version**: 1.0
**Last Updated**: 2025-12-04
**Total Issues**: 12
**Total Estimated Time**: 96 hours
**Expected Duration**: 6 weeks
