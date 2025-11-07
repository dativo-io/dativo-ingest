# Sprint Planning Template

**Sprint Number**: [e.g., Sprint 1]  
**Duration**: [e.g., 2 weeks]  
**Start Date**: [YYYY-MM-DD]  
**End Date**: [YYYY-MM-DD]  
**Sprint Goal**: [One-sentence objective]

---

## Team Capacity

| Team Member | Role | Availability | Capacity (hours) |
|-------------|------|--------------|------------------|
| [Name] | Engineer | 100% | 80 |
| [Name] | Engineer | 80% | 64 |
| [Name] | QA | 100% | 80 |

**Total Capacity**: [X] hours

---

## Sprint Backlog

### High Priority (P0)

#### Task 1: [Task Name]
- **Story Points**: [1-13]
- **Assignee**: [Name]
- **Dependencies**: [List dependencies]
- **Acceptance Criteria**:
  - [ ] Criterion 1
  - [ ] Criterion 2
  - [ ] Criterion 3
- **Technical Notes**:
  ```
  [Implementation details]
  ```

#### Task 2: [Task Name]
- **Story Points**: [1-13]
- **Assignee**: [Name]
- **Dependencies**: [List dependencies]
- **Acceptance Criteria**:
  - [ ] Criterion 1
  - [ ] Criterion 2
- **Technical Notes**:
  ```
  [Implementation details]
  ```

### Medium Priority (P1)

[Same format as above]

### Low Priority (P2)

[Same format as above]

---

## Definition of Done

A task is considered "Done" when:

- [ ] Code is written and follows style guide
- [ ] Unit tests written (>80% coverage)
- [ ] Integration tests written (if applicable)
- [ ] Code reviewed and approved by 2+ reviewers
- [ ] Documentation updated (docstrings, README)
- [ ] CI/CD pipeline passes
- [ ] Merged to main branch
- [ ] Deployed to staging environment
- [ ] Tested in staging by QA
- [ ] No critical/high severity bugs

---

## Sprint Schedule

### Week 1

| Day | Activities | Deliverables |
|-----|-----------|--------------|
| Mon | Sprint planning, environment setup | Sprint backlog finalized |
| Tue | Development: Task 1 | 40% complete |
| Wed | Development: Task 1 | 70% complete |
| Thu | Development: Task 1, code review | 100% complete, PR submitted |
| Fri | Development: Task 2 | 30% complete |

### Week 2

| Day | Activities | Deliverables |
|-----|-----------|--------------|
| Mon | Development: Task 2 | 70% complete |
| Tue | Development: Task 2, testing | 100% complete, tests written |
| Wed | Integration testing, bug fixes | All tests passing |
| Thu | Documentation, final review | Docs complete |
| Fri | Sprint review, retrospective | Sprint closed |

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| API rate limiting issues | High | Medium | Implement backoff early, test with production limits |
| Dependency on external service | Medium | Low | Mock services for testing |
| Team member unavailable | Low | Low | Cross-train on critical tasks |

---

## Technical Debt

Items to address in this sprint:

1. **[Debt Item 1]**
   - Impact: [High/Medium/Low]
   - Effort: [X hours]
   - Plan: [How to address]

2. **[Debt Item 2]**
   - Impact: [High/Medium/Low]
   - Effort: [X hours]
   - Plan: [How to address]

---

## Testing Plan

### Unit Tests
- [ ] Test connector initialization
- [ ] Test record extraction
- [ ] Test error handling
- [ ] Test state management

### Integration Tests
- [ ] Test end-to-end flow (extract → validate → write)
- [ ] Test with real API (test account)
- [ ] Test incremental sync

### Performance Tests
- [ ] Benchmark extraction speed (target: [X] records/sec)
- [ ] Memory usage under load (target: < [X] GB)
- [ ] Connection pooling effectiveness

---

## Sprint Ceremonies

### Daily Standup (15 min)
- **Time**: 9:00 AM daily
- **Format**:
  - What did I complete yesterday?
  - What will I work on today?
  - Any blockers?

### Mid-Sprint Check-in (30 min)
- **Time**: Wednesday, Week 1
- **Agenda**:
  - Review progress vs. plan
  - Adjust priorities if needed
  - Address blockers

### Sprint Review (60 min)
- **Time**: Friday, Week 2
- **Agenda**:
  - Demo completed work
  - Stakeholder feedback
  - Update roadmap if needed

### Sprint Retrospective (45 min)
- **Time**: Friday, Week 2
- **Agenda**:
  - What went well?
  - What could be improved?
  - Action items for next sprint

---

## Success Metrics

- **Velocity**: [X] story points completed
- **Burndown**: On track / Ahead / Behind
- **Code Quality**: [X]% test coverage
- **Bugs Found**: [X] critical, [X] high, [X] medium, [X] low
- **Team Satisfaction**: [1-5 rating]

---

## Notes

[Any additional notes, decisions, or context]

---

## Post-Sprint Actions

- [ ] Update sprint metrics in tracking system
- [ ] Create tasks for follow-up items
- [ ] Update technical documentation
- [ ] Plan next sprint
- [ ] Archive sprint artifacts

---

**Template Version**: 1.0  
**Last Updated**: 2025-11-07
