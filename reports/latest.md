# RAG Evaluation Report

Generated: `2026-09-10T20:54:26.313060+00:00`  
Dataset: **56 cases** (41 answerable, 15 unanswerable)  
Pipeline: **bm25 retrieval + extractive generation**
Benchmark SHA-256: `97b3e6aa14c0c474b0b9dec0e590c9f8fa8ee5b46a21a36eb6cd3667fb9275ed`

Quality metrics average answerable cases only. Unanswerable cases are scored by their abstention rate. N/A means the benchmark has no cases for that metric.

Required phrase coverage is literal text matching, not semantic correctness. Faithfulness checks exact cited source text, not truth or answer relevance.

## Aggregate metrics

| Metric | Value |
|---|---:|
| `hit_rate_at_3` | 1.0000 |
| `mean_reciprocal_rank` | 0.9878 |
| `source_recall_at_3` | 1.0000 |
| `required_phrase_coverage` | 0.8902 |
| `faithfulness` | 1.0000 |
| `citation_correctness` | 1.0000 |
| `answerable_response_rate` | 1.0000 |
| `unanswerable_abstention_rate` | 0.1333 |
| `p95_latency_ms` | 0.2380 |

## Quality gate: FAIL

| Metric | Actual | Required | Result |
|---|---:|---:|:---:|
| `hit_rate_at_3` | 1.0000 | >= 1.0000 | PASS |
| `mean_reciprocal_rank` | 0.9878 | >= 0.9000 | PASS |
| `source_recall_at_3` | 1.0000 | >= 0.9000 | PASS |
| `required_phrase_coverage` | 0.8902 | >= 0.8500 | PASS |
| `faithfulness` | 1.0000 | >= 1.0000 | PASS |
| `citation_correctness` | 1.0000 | >= 1.0000 | PASS |
| `answerable_response_rate` | 1.0000 | >= 1.0000 | PASS |
| `unanswerable_abstention_rate` | 0.1333 | >= 1.0000 | FAIL |
| `p95_latency_ms` | 0.2380 | <= 50.0000 | PASS |

## Case details

| Case | Category | Expected | Actual | Hit@3 | Source recall@3 | Phrase coverage | Issues |
|---|---|---|---|---:|---:|---:|---|
| refund-window | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| refund-request | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| sso-plan | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| log-retention | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| sev1-response | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| api-limit | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| export-link | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| owner-permissions | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| backup-schedule | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| enterprise-support | standard | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| monthly-refund-paraphrase | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| deleted-content-recovery | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| rate-limit-retry-paraphrase | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| severity-update-paraphrase | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| standard-support-hours-paraphrase | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| refund-seven-day-correction | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| admin-billing-correction | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| export-page-correction | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 0.5000 | Required phrases missing: ZIP file |
| sso-admin-correction | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| annual-discount-correction | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| export-and-recovery | multi_source | Answer | Answer | 1.0000 | 1.0000 | 0.5000 | Required phrases missing: expires after 24 hours |
| enterprise-sev1-support | multi_source | Answer | Answer | 1.0000 | 1.0000 | 0.5000 | Required phrases missing: within 15 minutes |
| sso-export-owner | multi_source | Answer | Answer | 1.0000 | 1.0000 | 0.5000 | Required phrases missing: Settings, Security, then Single sign-on |
| api-owner-sso-rate | multi_source | Answer | Answer | 1.0000 | 1.0000 | 0.5000 | Required phrases missing: An organization owner enables SSO |
| backup-export-retention | multi_source | Answer | Answer | 1.0000 | 1.0000 | 0.6667 | Required phrases missing: ZIP file |
| unans-chess | no_overlap | Abstain | Abstain | N/A | N/A | N/A | — |
| unans-mona-lisa | no_overlap | Abstain | Abstain | N/A | N/A | N/A | — |
| unans-support-phone | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| unans-api-endpoint | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| unans-sso-provider-list | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| conflicting-upload-limit | conflicting_sources | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| conflicting-upload-cap | conflicting_sources | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| par-refund-eligibility | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| par-sso-plan | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| par-backup-rpo | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| par-support-priority-window | paraphrase | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| inc-downgrade-timing | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| inc-api-rate-limit | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| inc-recovery-window | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| inc-backup-frequency | incorrect_premise | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| multi-admin-sso-export | multi_source | Answer | Answer | 1.0000 | 1.0000 | 0.3333 | Required phrases missing: Admins manage members and integrations.; The export is delivered as a ZIP file through a signed link that expires after 24 hours. |
| multi-severity-support-targets | multi_source | Answer | Answer | 1.0000 | 1.0000 | 0.5000 | Required phrases missing: A Severity 1 incident is a complete production outage or confirmed data exposure affecting multiple customers. |
| multi-billing-logs | multi_source | Answer | Answer | 1.0000 | 1.0000 | 0.5000 | Required phrases missing: Paid plans can be billed monthly or annually. |
| multi-backups-downgrade | multi_source | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| boundary-rate-limit | boundary_conditions | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| boundary-refund-renewal | boundary_conditions | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| boundary-recovery-window | boundary_conditions | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| boundary-support-hours | boundary_conditions | Answer | Answer | 1.0000 | 1.0000 | 1.0000 | — |
| missing-reset-header | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| missing-verified-domain-format | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| missing-idp-metadata-format | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| missing-export-signing-key | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| missing-backup-region | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| missing-audit-log-base | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| missing-severity-two-response | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |
| missing-export-concurrency | missing_info | Abstain | Answer | N/A | N/A | N/A | Expected abstention; returned an answer |

## Failure evidence

### export-page-correction

Question: Is the full workspace export started from Integrations and sent as a PDF attachment?

Answer: Organization owners can start a full workspace export from Settings, Data, then Export. [data-export] Only organization owners can change billing, delete a workspace, configure SSO, or start a full data export. [roles-permissions]

Retrieved: roles-permissions, data-export, attachment-guide-a

Expected sources: data-export

Issues: Required phrases missing: ZIP file

### export-and-recovery

Question: How long is a workspace export download link valid, and how long can deleted workspace content be recovered?

Answer: Deleted workspace content enters a 14-day recovery window before permanent deletion. [retention-policy] Organization owners can start a full workspace export from Settings, Data, then Export. [data-export]

Retrieved: data-export, retention-policy, roles-permissions

Expected sources: data-export, retention-policy

Issues: Required phrases missing: expires after 24 hours

### enterprise-sev1-support

Question: What acknowledgment time and support coverage apply to Severity 1 incidents for Enterprise customers?

Answer: Enterprise customers receive 24/7 support for Severity 1 incidents. [support-hours] A Severity 1 incident is a complete production outage or confirmed data exposure affecting multiple customers. [incident-severity]

Retrieved: support-hours, incident-severity, retention-policy

Expected sources: incident-severity, support-hours

Issues: Required phrases missing: within 15 minutes

### sso-export-owner

Question: Where does an organization owner enable SSO and start a full workspace export?

Answer: Only organization owners can change billing, delete a workspace, configure SSO, or start a full data export. [roles-permissions] Organization owners can start a full workspace export from Settings, Data, then Export. [data-export]

Retrieved: data-export, roles-permissions, sso-setup

Expected sources: sso-setup, data-export

Issues: Required phrases missing: Settings, Security, then Single sign-on

### api-owner-sso-rate

Question: Who enables SSO, and which status code is returned when the public API rate limit is exceeded?

Answer: When the limit is exceeded, the service returns HTTP 429 and clients should retry with exponential backoff. [api-limits] The public API allows 600 requests per minute per workspace. [api-limits]

Retrieved: api-limits, sso-setup, roles-permissions

Expected sources: sso-setup, api-limits

Issues: Required phrases missing: An organization owner enables SSO

### backup-export-retention

Question: In what format are workspace exports delivered, how long are Standard application logs retained, and how long are daily backups retained?

Answer: Application logs are retained for 90 days on the Standard plan and 365 days on the Enterprise plan. [retention-policy] Daily backups are retained for 35 days. [backups]

Retrieved: retention-policy, backups, data-export

Expected sources: data-export, retention-policy, backups

Issues: Required phrases missing: ZIP file

### unans-support-phone

Question: What is the phone number for 24/7 support for incident response?

Answer: Enterprise customers receive 24/7 support for Severity 1 incidents. [support-hours] The target first response for standard-priority tickets is one business day. [support-hours]

Retrieved: support-hours, incident-severity, refund-policy

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### unans-api-endpoint

Question: What is the base URL of the public API?

Answer: The public API allows 600 requests per minute per workspace. [api-limits] The identity provider metadata URL and verified company domain are required before activation. [sso-setup]

Retrieved: api-limits, sso-setup

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### unans-sso-provider-list

Question: Besides SAML, which identity providers are supported for SSO in this product?

Answer: The identity provider metadata URL and verified company domain are required before activation. [sso-setup] SAML single sign-on is available on the Enterprise plan. [sso-setup]

Retrieved: sso-setup, support-hours, roles-permissions

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### conflicting-upload-limit

Question: What is the maximum attachment upload size?

Answer: The maximum attachment upload size is 25 MB. [attachment-guide-a] The maximum attachment upload size is 100 MB. [attachment-guide-b]

Retrieved: attachment-guide-a, attachment-guide-b

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### conflicting-upload-cap

Question: How large can an uploaded attachment be?

Answer: The maximum attachment upload size is 25 MB. [attachment-guide-a] The maximum attachment upload size is 100 MB. [attachment-guide-b]

Retrieved: attachment-guide-a, attachment-guide-b, data-export

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### multi-admin-sso-export

Question: What do admins manage, which prerequisites are required before SSO activation, and what format is used for full workspace exports?

Answer: Only organization owners can change billing, delete a workspace, configure SSO, or start a full data export. [roles-permissions] The identity provider metadata URL and verified company domain are required before activation. [sso-setup]

Retrieved: roles-permissions, sso-setup, data-export

Expected sources: roles-permissions, sso-setup, data-export

Issues: Required phrases missing: Admins manage members and integrations.; The export is delivered as a ZIP file through a signed link that expires after 24 hours.

### multi-severity-support-targets

Question: What defines a Severity 1 incident, and what is the first-response target for standard-priority tickets?

Answer: The target first response for standard-priority tickets is one business day. [support-hours] Enterprise customers receive 24/7 support for Severity 1 incidents. [support-hours]

Retrieved: support-hours, incident-severity, retention-policy

Expected sources: incident-severity, support-hours

Issues: Required phrases missing: A Severity 1 incident is a complete production outage or confirmed data exposure affecting multiple customers.

### multi-billing-logs

Question: Which billing frequencies are valid, and how do application-log retention windows differ by plan?

Answer: Audit-log retention can be extended by contract. [retention-policy] Application logs are retained for 90 days on the Standard plan and 365 days on the Enterprise plan. [retention-policy]

Retrieved: retention-policy, billing-cycle, roles-permissions

Expected sources: billing-cycle, retention-policy

Issues: Required phrases missing: Paid plans can be billed monthly or annually.

### missing-reset-header

Question: What is the exact response header name that indicates when the rate limit resets?

Answer: Responses include the X-RateLimit-Remaining header. [api-limits] When the limit is exceeded, the service returns HTTP 429 and clients should retry with exponential backoff. [api-limits]

Retrieved: api-limits, data-export, incident-severity

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### missing-verified-domain-format

Question: What is the exact accepted format for a verified company domain during SSO setup?

Answer: The identity provider metadata URL and verified company domain are required before activation. [sso-setup] An organization owner enables SSO under Settings, Security, then Single sign-on. [sso-setup]

Retrieved: sso-setup, roles-permissions

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### missing-idp-metadata-format

Question: What is the exact required format of the identity provider metadata URL used for SSO activation?

Answer: The identity provider metadata URL and verified company domain are required before activation. [sso-setup] An organization owner enables SSO under Settings, Security, then Single sign-on. [sso-setup]

Retrieved: sso-setup, roles-permissions

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### missing-export-signing-key

Question: Which signing algorithm is used for the export signed link, and what key rotation policy applies?

Answer: The export is delivered as a ZIP file through a signed link that expires after 24 hours. [data-export] Large exports can take up to 6 hours to prepare. [data-export]

Retrieved: data-export, sso-setup, refund-policy

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### missing-backup-region

Question: Which physical region hosts the separate encrypted backup storage location?

Answer: Encrypted database backups run every 6 hours and are stored in a separate region. [backups] Daily backups are retained for 35 days. [backups]

Retrieved: backups

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### missing-audit-log-base

Question: What is the default audit-log retention duration if no contract extension is purchased?

Answer: Audit-log retention can be extended by contract. [retention-policy]

Retrieved: retention-policy

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### missing-severity-two-response

Question: What is the documented response time target for Severity 2 incidents?

Answer: Enterprise customers receive 24/7 support for Severity 1 incidents. [support-hours] The target first response for standard-priority tickets is one business day. [support-hours]

Retrieved: support-hours, incident-severity, api-limits

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

### missing-export-concurrency

Question: What is the maximum number of full workspace exports that can run simultaneously?

Answer: Organization owners can start a full workspace export from Settings, Data, then Export. [data-export] Only organization owners can change billing, delete a workspace, configure SSO, or start a full data export. [roles-permissions]

Retrieved: data-export, roles-permissions, refund-policy

Expected sources: None (unanswerable)

Issues: Expected abstention; returned an answer

