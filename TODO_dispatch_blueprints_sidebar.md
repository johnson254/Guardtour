# TODO: Dispatch Guard Tour Command - Blueprint Sidebar

- [ ] Step 1: Update `templates/dispatch.html` left area when `currentTab === 'blueprints'` to show 2 sections: On-going + Available.
- [ ] Step 2: Add click handler on each blueprint card:
  - set `dcRoute` value
  - call `dcOnRouteSelect()`
  - ensure right command panel is visible (`dcShowCommand()`)
- [ ] Step 3: Add Deploy/View buttons in the sidebar cards:
  - Deploy uses `dcSetRouteForDeploy(routeId)` or quick deploy helper
  - View uses `dcViewBlueprintAssignments(routeId)`
- [ ] Step 4: Ensure mission list highlighting still works (after `View`).
- [ ] Step 5: Verify “Missed” tab still works with left sidebar changes.

