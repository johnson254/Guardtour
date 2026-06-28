# TODO — Routes Blueprint UX modernization

- [ ] 1) Merge TTS Announcement + Description/Mission Briefing into one briefing control with a broadcast switch (map to existing backend fields).
- [ ] 2) Group Daily Recurrence + Lead time together with improved icons/UX.
- [ ] 3) Create unified Execution Timeline control (date+time) or visually tie them together.
- [ ] 4) Add “real world logic” UI validation to prevent Save/Deploy when:
  - [ ] start alert window is past due when scheduling for today
  - [ ] launch start is already past
  - [ ] any checkpoint planned_time is already past (for today)
- [ ] 5) Reduce Point Name input density:
  - [ ] auto-fill point name from selected asset/NFC
  - [ ] hide Point Name field by default for NFC/GPS; show only when rename needed
- [ ] 6) Modernize checkpoint viewing:
  - [ ] improve chips/labels (TGT/GAP/TOL, ON TIME vs MISSED)
  - [ ] consistent quick actions placement
- [ ] 7) Manual verification checklist (after implementing):
  - [ ] attempt Save & Deploy with past-due times => blocked with toast
  - [ ] checkpoint planned_time past => blocked or highlighted
  - [ ] point name auto-fills => no extra typing required
  - [ ] merged briefing switch populates correct fields


