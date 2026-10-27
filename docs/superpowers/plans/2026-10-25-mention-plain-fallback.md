# Unique WeChat mention with plain-text fallback

User explicitly requests: type @ then the group nickname; click only when exactly one matching member is visible. Two members, no member or no accessible picker sends the body without a mention. This supersedes the earlier block-on-missing/ambiguous-picker rule.

1. Add failing fake-UI cases for absent panel, zero/two candidates, one exact plus another prefix, focus/draft interference and cleanup failure. Preserve real-object verification for successful selection.
2. Type the nickname before requiring picker discovery. Recognize newly visible inline candidate lists within the verified chat as well as newly owned popups. Exclude pre-existing session/message lists.
3. Use a bounded fallback state machine: verify the exact bot-owned draft, dismiss picker, select the draft, recheck ownership/focus, erase, verify empty. Never press Enter during mention selection or cleanup. Unknown/user-modified drafts remain blocked.
4. TypingSession continues normal body-only verification after successful cleanup; submitted_text contains only body. Persist a scalar fallback reason in existing delivery logs and expose a plain-text fallback stage.
5. Run focused offline tests and full suite as needed, update documentation. Do not restart services or send real WeChat tests. Existing blocked deliveries remain for explicit administrative handling.

Completed and independently reviewed. Empty-name visible candidate rows count toward ambiguity; replaced/unreadable embedded objects are preserved rather than erased. Tests cover candidate controls deeper than 15 levels using the configured chat search depth, stale picker lookup, absent/ambiguous selectors, cleanup failure, draft interference and final body-only submission. Full offline suite: 663 tests, 660 passed, 3 unchanged baseline failures, 0 errors/skips, 40.279 seconds. Evidence: .superpowers/mention-fallback-final.xml and .txt. Python/JavaScript syntax and git diff --check passed. No real WeChat test sends, clipboard access or service restart. User must reload wxbot and log; prior manual-required tasks are not automatically released or replayed.
