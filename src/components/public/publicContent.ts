import type { PolicyPageProps } from "@/components/public/PolicyPage";

export const PUBLIC_CONTENT_UPDATED = "July 27, 2026";

export const publicPages = {
  privacy: {
    eyebrow: "Legal",
    title: "Privacy policy",
    description:
      "An initial, plain-language account of the information ZeroOps AI processes when you connect source code, prepare a deployment, and operate an application.",
    current: "legal",
    documentStatus: "Draft — legal review required",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "This page is an implementation-informed placeholder, not a finalized privacy notice. The operating company name, registered address, privacy contact, retention schedule, and governing jurisdiction must be completed before production launch.",
    noticeTone: "caution",
    sections: [
      {
        id: "scope",
        title: "Scope and operator",
        paragraphs: [
          "This notice describes the current ZeroOps AI application. The service operator is [company legal name — pending legal review], at [registered address — pending legal review].",
          "It covers the public site, authenticated workspace, repository intake, infrastructure planning, deployment workflow, and the logs or monitoring records available in the workspace.",
        ],
      },
      {
        id: "information",
        title: "Information we process",
        bullets: [
          "Account information, such as name, email address, authentication provider, account settings, and security-verification records.",
          "GitHub account and repository metadata when you connect GitHub, including repository name, owner, branch, visibility, language, and update time.",
          "GitHub source code that you select for analysis and deployment preparation, plus uploaded ZIP contents used for analysis only in the current deployment topology.",
          "Repository-analysis results, including detected framework, runtime, build and start commands, dependency names, environment-variable names, and deployment requirements.",
          "Azure connection and cloud-resource metadata needed to prepare and run an approved App Service deployment. Secret values are handled server-side and are not returned in normal secret-list responses.",
          "Deployment records, worker progress, logs, audit events, and monitoring metrics when those records exist.",
          "Technical request data needed to secure and operate the service, such as session, CSRF, and OAuth state information.",
        ],
      },
      {
        id: "source-code",
        title: "Source-code processing",
        paragraphs: [
          "ZeroOps AI processes only the repository or ZIP that you choose. GitHub source can be prepared for an approved deployment job; ZIP contents are analysis-only until durable worker-accessible source storage is configured.",
          "Repository analysis currently runs in the control-plane workflow with deterministic local inspection available. It is not a claim that a separate security-scanning worker, remediation worker, or compliance scanner has reviewed the code.",
        ],
        note:
          "Do not include credentials in source code or uploads. Configure runtime secrets through the authenticated workspace.",
      },
      {
        id: "purposes",
        title: "Why we use information",
        bullets: [
          "Create and secure your account and authenticated session.",
          "Import the source you select and identify deployment requirements.",
          "Generate a reviewable Azure App Service infrastructure plan.",
          "Queue and execute a deployment only after the required approval.",
          "Display deployment status, stored logs, audit history, and available monitoring data.",
          "Diagnose failures, protect the service, and respond to support or legal requests.",
        ],
      },
      {
        id: "ai-processing",
        title: "AI-provider processing",
        paragraphs: [
          "When a model provider is configured, selected repository context and project metadata may be sent to that provider to produce analysis or explanatory output. The configured provider, region, retention behavior, and contractual terms must be documented by the service operator before launch.",
          "If the remote model path is unavailable, the repository includes a local deterministic analysis path. AI output is advisory and does not remove the infrastructure approval boundary.",
        ],
      },
      {
        id: "retention",
        title: "Retention and deletion",
        paragraphs: [
          "The application stores account, project, analysis, plan, deployment, log, metric, and audit records needed for the workspace. Temporary GitHub working copies are removed after supported processing paths; uploaded ZIP analysis artifacts follow project retention and do not yet have a published retention period.",
          "A formal retention schedule, backup-deletion schedule, and verified account-deletion procedure are not yet published. Requests should be sent to [privacy contact email — pending legal review] once that channel is active.",
        ],
      },
      {
        id: "safeguards",
        title: "Security measures",
        bullets: [
          "HttpOnly session and refresh cookies, CSRF checks for unsafe cookie-authenticated requests, and protected authenticated routes.",
          "Project ownership checks on sensitive project-scoped APIs.",
          "Production configuration designed to load application secrets through Azure Key Vault using managed identity.",
          "A dedicated deployment worker for queued Azure build and App Service deployment activity.",
          "Upload validation and archive-extraction limits for submitted ZIP files.",
        ],
        note:
          "These are implementation controls, not a certification. ZeroOps AI does not currently claim SOC 2, ISO 27001, HIPAA, GDPR certification, or any equivalent assurance.",
      },
      {
        id: "rights-contact",
        title: "Requests and contact",
        paragraphs: [
          "Depending on your location, you may have rights to access, correct, delete, or restrict use of personal information. The service operator must confirm applicable rights and response procedures with legal counsel.",
          "Privacy contact: [privacy contact email — pending legal review]. Legal entity, postal address, representative details, and regulator contact information remain to be completed.",
        ],
      },
    ],
  },
  terms: {
    eyebrow: "Legal",
    title: "Terms of service",
    description:
      "Initial terms for using a source-to-Azure deployment workflow where repository access, infrastructure approval, and cloud charges remain under the user’s control.",
    current: "legal",
    documentStatus: "Draft — legal review required",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "These draft terms are not a finalized contract. Company identity, pricing terms, service levels, liability language, governing law, dispute process, and contact details require legal and commercial approval.",
    noticeTone: "caution",
    sections: [
      {
        id: "operator",
        title: "Service operator and acceptance",
        paragraphs: [
          "ZeroOps AI is operated by [company legal name — pending legal review]. These terms are intended to govern access to the public site and authenticated application once formally adopted.",
          "A production launch must present the final terms and a recorded acceptance mechanism. Continued use language alone should not replace a clear acceptance flow where one is legally required.",
        ],
      },
      {
        id: "accounts",
        title: "Accounts and responsibilities",
        bullets: [
          "Provide accurate account information and keep authentication methods secure.",
          "Use only repositories, Azure subscriptions, domains, and data you are authorized to access.",
          "Review repository permissions, environment configuration, infrastructure plans, and deployment targets before approval.",
          "Notify the service operator promptly if you believe an account or integration has been compromised.",
        ],
      },
      {
        id: "source-data",
        title: "Your source code and data",
        paragraphs: [
          "You retain ownership of source code and other material you submit. You grant the service operator the limited permission needed to import, inspect, store, prepare, and deploy that material at your direction.",
          "You are responsible for ensuring the submitted material does not include unlawfully obtained data, embedded credentials, malware, or content that violates third-party rights.",
        ],
      },
      {
        id: "deployments",
        title: "Plans, approvals, and deployments",
        paragraphs: [
          "ZeroOps AI prepares a reviewable infrastructure plan. The current deployment engine supports approved Azure App Service plans. Changing a plan returns it to draft and requires approval again.",
          "An approval authorizes the service to queue the represented deployment work. It does not authorize undisclosed resources or guarantee that Azure will accept or successfully provision every requested resource.",
        ],
      },
      {
        id: "cloud-costs",
        title: "Cloud-provider charges",
        paragraphs: [
          "Azure and other third-party provider charges are separate from any ZeroOps AI fees unless a final order form expressly says otherwise. Estimates shown in the product are planning aids and may differ from the final provider bill.",
          "You remain responsible for reviewing the selected subscription, region, service tier, scaling settings, and resulting provider charges before approval.",
        ],
      },
      {
        id: "recommendations",
        title: "Analysis and recommendations",
        paragraphs: [
          "Repository analysis and AI-generated explanations are advisory. They may be incomplete or incorrect and are not a substitute for code review, security testing, legal review, or professional cloud architecture advice.",
          "The current product must not be treated as proof that a dedicated security scanner, compliance program, or continuous remediation system has evaluated an application.",
        ],
      },
      {
        id: "availability",
        title: "Availability and warranties",
        paragraphs: [
          "No uptime commitment or public service-level agreement is currently published. The final agreement must define maintenance, support, warranty disclaimers, remedies, and any service credits.",
          "[Warranty, limitation-of-liability, indemnity, and force-majeure language — pending legal review.]",
        ],
      },
      {
        id: "termination",
        title: "Suspension, termination, and contact",
        paragraphs: [
          "Access may be suspended for material security risk, unlawful use, non-payment under future commercial terms, or a serious breach of the finalized agreement. The final terms must define notice, export, deletion, and appeal procedures.",
          "Governing law: [jurisdiction — pending legal review]. Legal contact: [legal contact email — pending legal review].",
        ],
      },
    ],
  },
  security: {
    eyebrow: "Trust",
    title: "Security at ZeroOps AI",
    description:
      "A factual view of the controls present in the current application, the approval boundary around cloud changes, and the security capabilities that are not yet separate worker services.",
    current: "security",
    documentStatus: "Implementation overview — not a certification",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "This page describes repository controls visible in the current implementation. It is not an audit report, penetration-test result, compliance attestation, or promise that every deployment is secure.",
    sections: [
      {
        id: "security-model",
        title: "Security model",
        paragraphs: [
          "ZeroOps AI separates its authenticated control plane from its queued deployment worker. Users select source code, review derived deployment evidence, approve an App Service plan, and then initiate the deployment.",
          "The approval boundary is enforced by the backend: a deployment cannot start without an approved infrastructure plan, and editing that plan returns it to draft.",
        ],
      },
      {
        id: "identity-access",
        title: "Identity and access",
        bullets: [
          "Browser sessions use HttpOnly session and refresh cookies.",
          "Unsafe cookie-authenticated requests are checked with a CSRF token.",
          "Sensitive project APIs require authentication and validate project ownership.",
          "OAuth state is validated for connected identity-provider flows.",
          "Multi-factor authentication paths are present for supported account flows.",
        ],
      },
      {
        id: "secrets",
        title: "Secrets and Azure identity",
        paragraphs: [
          "Production configuration is designed to retrieve backend and worker settings from Azure Key Vault through DefaultAzureCredential. Managed identity is the intended Azure authentication mechanism; credentials must not be embedded in frontend code.",
          "Secret-list APIs return secret metadata rather than the stored secret value. Users should still avoid placing credentials in repositories, ZIP files, deployment logs, or support messages.",
        ],
      },
      {
        id: "worker-isolation",
        title: "Deployment-worker isolation",
        paragraphs: [
          "Azure image builds, App Service provisioning and updates, application deployment, and public-endpoint validation are queued for a dedicated deployment worker. The FastAPI control plane records and coordinates the job rather than running that privileged deployment path itself.",
          "ZeroOps AI does not currently claim that repository analysis, security scanning, monitoring collection, or remediation each run in separate isolated workers. Those must be treated as future architecture until implemented and verified.",
        ],
      },
      {
        id: "source-upload",
        title: "Repository and upload safeguards",
        bullets: [
          "Users choose the GitHub repository and branch that enters the workspace.",
          "ZIP intake restricts accepted archive type and applies file-count, expanded-size, and compression-ratio limits.",
          "ZIP uploads are analysis-only. Deployment workers require GitHub-backed source until durable shared source storage is configured.",
          "Archive extraction checks are intended to prevent files from escaping the temporary workspace.",
          "Temporary working copies are removed by supported processing paths after analysis completes.",
        ],
      },
      {
        id: "audit-visibility",
        title: "Audit and operational visibility",
        paragraphs: [
          "The data model records infrastructure-plan revisions and approvals, deployment jobs, deployment logs, and user or system activity. The workspace presents logs and monitoring values only when corresponding records exist.",
          "Deployment logs are persisted in the application database. Live WebSocket delivery is best-effort, while cross-restart history depends on database availability and the operator's retention policy.",
        ],
      },
      {
        id: "assurance-boundary",
        title: "Assurance boundary",
        bullets: [
          "No SOC 2, ISO 27001, HIPAA, PCI DSS, or government authorization is claimed.",
          "No dedicated SAST, dependency-scanning, secret-scanning, container-scanning, or compliance worker is represented as active.",
          "No public penetration-test report, bug-bounty program, uptime SLA, or external security audit is currently published.",
          "Encryption at rest, backup, network-isolation, and regional controls depend on the services and production configuration selected by the operator and customer.",
        ],
      },
      {
        id: "report",
        title: "Report a vulnerability",
        paragraphs: [
          "The responsible-disclosure process is documented separately. The final security inbox and response commitments are still pending.",
        ],
        note:
          "Do not send credentials, access tokens, private source code, or exploit payloads to a placeholder address.",
      },
    ],
  },
  responsibleDisclosure: {
    eyebrow: "Trust",
    title: "Responsible disclosure",
    description:
      "Guidance for reporting a suspected security issue without putting customer data, cloud resources, or service availability at risk.",
    current: "security",
    documentStatus: "Draft process — intake address pending",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "The dedicated security intake address and legal safe-harbor language have not been finalized. Do not submit sensitive material until a verified channel is published.",
    noticeTone: "caution",
    sections: [
      {
        id: "reporting-channel",
        title: "Reporting channel",
        paragraphs: [
          "Planned security contact: [security contact email — pending configuration]. The address must be verified and monitored before this process is considered operational.",
          "For a non-sensitive coordination question, use the public contact page. Never place credentials, tokens, private repository content, or personal data in an unverified message.",
        ],
      },
      {
        id: "scope",
        title: "Intended scope",
        bullets: [
          "Authentication or authorization bypass in the ZeroOps AI application.",
          "Cross-project access to repository, deployment, secret, metric, or log records.",
          "Server-side request, archive-extraction, injection, or code-execution vulnerabilities.",
          "Exposure of session material, OAuth tokens, cloud credentials, or stored secrets.",
          "A worker-control flaw that could cause an unapproved or cross-tenant deployment action.",
        ],
      },
      {
        id: "research-rules",
        title: "Research rules",
        bullets: [
          "Use only accounts, repositories, subscriptions, and data you own or are explicitly authorized to test.",
          "Do not perform denial-of-service testing, social engineering, phishing, physical intrusion, or destructive cloud actions.",
          "Stop immediately if you encounter another user’s information and record only the minimum evidence needed to explain the issue.",
          "Do not retain, share, modify, or publicly disclose customer data.",
          "Do not demand payment or threaten disclosure.",
        ],
      },
      {
        id: "report-content",
        title: "What to include",
        bullets: [
          "A concise description and the affected route, component, or workflow.",
          "Reproduction steps using a test account and non-sensitive sample data.",
          "Observed and expected behavior.",
          "Potential impact and any prerequisite permissions.",
          "A safe proof of concept, with secrets and personal data removed.",
          "A contact method and your preferred attribution, if any.",
        ],
      },
      {
        id: "response",
        title: "What to expect",
        paragraphs: [
          "The final process should define acknowledgement, triage, remediation, and disclosure-coordination targets. No response-time SLA or bounty is offered by this draft page.",
          "Reports may be closed as duplicates, informational findings, unsupported third-party issues, or risks that require no product change. The operator should explain that decision where practical.",
        ],
      },
      {
        id: "safe-harbor",
        title: "Safe-harbor placeholder",
        paragraphs: [
          "[Good-faith research and safe-harbor language — pending legal review.] Until adopted, this page must not be interpreted as authorization to access systems or data beyond your existing permission.",
        ],
      },
    ],
  },
  dataProcessing: {
    eyebrow: "Data & privacy",
    title: "Data processing and retention",
    description:
      "An implementation-oriented summary of data categories, processing purposes, storage boundaries, and the decisions still required for a formal data-processing agreement.",
    current: "legal",
    documentStatus: "Draft overview — not a signed DPA",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "Controller/processor roles, processing locations, transfer terms, deletion deadlines, audit rights, and the legal entity details require counsel and customer-contract review.",
    noticeTone: "caution",
    sections: [
      {
        id: "roles",
        title: "Roles and instructions",
        paragraphs: [
          "The expected model is that a customer determines what repository and cloud account to connect, while [company legal name — pending] processes that material to provide ZeroOps AI. The parties must confirm controller, processor, and service-provider roles for each data category and jurisdiction.",
          "ZeroOps AI should process customer content only on documented instructions expressed through the product, a support request, and the finalized agreement.",
        ],
      },
      {
        id: "categories",
        title: "Data categories",
        bullets: [
          "Account, identity-provider, MFA, and session metadata.",
          "GitHub repository metadata and access material for a user-authorized connection.",
          "Selected source code, ZIP uploads, and derived repository-analysis records.",
          "Infrastructure plans, Azure connection metadata, deployment jobs, logs, and activity records.",
          "Monitoring metrics and cloud-resource metadata when those records are available.",
          "Support, security, privacy, and billing correspondence when those channels are enabled.",
        ],
      },
      {
        id: "purposes",
        title: "Processing purposes",
        bullets: [
          "Authenticate users and protect account access.",
          "Inspect selected source code and derive deployment requirements.",
          "Prepare, revise, and record an Azure App Service infrastructure plan.",
          "Run an explicitly approved deployment through the dedicated worker.",
          "Present deployment progress, stored logs, audit events, and available metrics.",
          "Secure, troubleshoot, and improve the service.",
        ],
      },
      {
        id: "retention",
        title: "Retention",
        paragraphs: [
          "The application stores persistent workspace records in its configured database and uses temporary filesystem locations during supported clone and upload-processing paths. Those temporary paths are removed after processing where implemented.",
          "Exact retention periods for accounts, source artifacts, logs, metrics, audit history, backups, and deleted records are not yet established in a published schedule. A production DPA must define them.",
        ],
      },
      {
        id: "deletion-return",
        title: "Return and deletion",
        paragraphs: [
          "Project and account deletion behavior, backup expiry, export format, and post-termination return of customer data must be verified end to end before contractual commitments are made.",
          "Deletion requests: [privacy contact email — pending legal review]. The operator must authenticate a requester before acting on account or project data.",
        ],
      },
      {
        id: "security",
        title: "Processing security",
        bullets: [
          "Authenticated, project-scoped API access for sensitive workspace records.",
          "HttpOnly session cookies and CSRF validation for unsafe browser requests.",
          "Production secret configuration through Azure Key Vault and managed identity.",
          "Dedicated deployment-worker execution for Azure build and App Service deployment work.",
          "Approval enforcement before a deployable App Service plan can be queued.",
        ],
      },
      {
        id: "providers",
        title: "Third-party processing",
        paragraphs: [
          "Microsoft Azure, GitHub, and a deployment-configured AI model provider may process customer data depending on the integrations a customer and operator enable. The subprocessor page distinguishes supported integrations from a finalized contractual list.",
          "International transfer mechanisms, provider regions, and customer notice procedures remain to be completed.",
        ],
      },
      {
        id: "dpa",
        title: "DPA availability",
        paragraphs: [
          "No signed standard data-processing addendum is published by this repository. [DPA request process, legal contact, SCCs or other transfer terms, and security schedule — pending legal review.]",
        ],
      },
    ],
  },
  subprocessors: {
    eyebrow: "Data & privacy",
    title: "Third-party services and subprocessors",
    description:
      "A transparent inventory of integrations the current product can use, without presenting unverified providers or contractual commitments as active.",
    current: "legal",
    documentStatus: "Implementation inventory — contractual list pending",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "Actual providers, legal entities, processing regions, data categories, and contract dates vary by deployment configuration and must be verified before this becomes a formal subprocessor notice.",
    noticeTone: "caution",
    sections: [
      {
        id: "azure",
        title: "Microsoft Azure",
        paragraphs: [
          "Purpose: application hosting, Azure App Service deployment, managed identity, Key Vault configuration, database and operational services selected by the service operator or customer.",
          "Data may include account and project records, encrypted configuration, deployment artifacts, logs, metrics, and cloud-resource metadata. Exact services and regions depend on the production environment.",
        ],
      },
      {
        id: "github",
        title: "GitHub",
        paragraphs: [
          "Purpose: optional OAuth authentication, repository discovery, branch selection, and source retrieval when a user connects GitHub.",
          "Data may include GitHub identity details, repository metadata, authorization tokens held server-side, and the contents of the repository a user selects.",
        ],
      },
      {
        id: "ai-provider",
        title: "Configured AI model provider",
        paragraphs: [
          "Purpose: optional AI-enriched repository analysis, explanations, and architect-chat responses. The codebase supports a configured provider and a deterministic local fallback.",
          "The operator must disclose the actual provider, model endpoint, processing region, data retention, and training-use terms. This page does not assume a provider is enabled.",
        ],
      },
      {
        id: "conditional",
        title: "Conditional integrations",
        paragraphs: [
          "Email, SMS, payment, and other provider integrations may exist in configuration paths without being active in a particular deployment. They must not be added to the contractual subprocessor list until enabled and verified.",
        ],
      },
      {
        id: "changes",
        title: "Provider changes",
        paragraphs: [
          "The finalized process should define how customers are notified before a new subprocessor begins processing customer content and how objections are handled.",
          "[Notification period, subscription mechanism, objection process, and effective-date history — pending legal review.]",
        ],
      },
      {
        id: "contact",
        title: "Questions",
        paragraphs: [
          "Subprocessor and DPA contact: [privacy or legal contact email — pending legal review]. Do not send private source code, credentials, or access tokens through an unverified public channel.",
        ],
      },
    ],
  },
  acceptableUse: {
    eyebrow: "Legal",
    title: "Acceptable use policy",
    description:
      "Baseline rules intended to protect users, repositories, worker capacity, and connected cloud accounts from abuse.",
    current: "legal",
    documentStatus: "Draft — legal review required",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "This policy is initial product guidance. Enforcement standards, notices, appeals, jurisdiction-specific restrictions, and legal contact details require review before launch.",
    noticeTone: "caution",
    sections: [
      {
        id: "authorized-use",
        title: "Use only what you control",
        paragraphs: [
          "Use ZeroOps AI only with accounts, repositories, code, domains, subscriptions, and data that you own or are explicitly authorized to access and deploy.",
          "Do not use a deployment approval to conceal or exceed the permission granted by a repository owner, organization administrator, or Azure subscription owner.",
        ],
      },
      {
        id: "unlawful-harmful",
        title: "Unlawful or harmful activity",
        bullets: [
          "Do not use the service to violate law, regulation, court order, sanctions, or third-party rights.",
          "Do not deploy malware, credential theft, phishing, botnets, ransomware, exploit kits, or content intended to facilitate harm.",
          "Do not upload or process personal, confidential, export-controlled, or regulated data without the authority and safeguards required for that data.",
          "Do not use the service for harassment, threats, fraud, impersonation, or deceptive activity.",
        ],
      },
      {
        id: "security-abuse",
        title: "Security abuse",
        bullets: [
          "Do not bypass authentication, approval, tenancy, rate, worker, or Azure permission boundaries.",
          "Do not scan or test systems you do not own or have explicit permission to assess.",
          "Do not attempt to retrieve another user’s source, secrets, logs, metrics, plans, or deployment artifacts.",
          "Do not probe the service in a way that degrades availability or risks customer data.",
        ],
      },
      {
        id: "resource-abuse",
        title: "Resource and platform abuse",
        bullets: [
          "Do not intentionally exhaust upload, database, queue, worker, network, or cloud-provider capacity.",
          "Do not evade limits by creating multiple accounts, projects, or integrations.",
          "Do not use the service for unauthorized cryptocurrency mining, traffic laundering, or high-risk workloads prohibited by the connected provider.",
        ],
      },
      {
        id: "source-secrets",
        title: "Source code and secrets",
        paragraphs: [
          "Do not submit code you cannot license for the requested processing. Remove embedded secrets before import and configure runtime values through the authenticated secret workflow.",
          "You are responsible for reviewing generated recommendations and the approved infrastructure plan before deployment.",
        ],
      },
      {
        id: "enforcement",
        title: "Enforcement and appeal",
        paragraphs: [
          "The operator may restrict activity that creates an immediate security, legal, or service-availability risk. The final policy must define investigation, notice, evidence preservation, appeal, and data-access procedures.",
          "Report abuse or appeal an action at [abuse contact email — pending legal review].",
        ],
      },
    ],
  },
  cookies: {
    eyebrow: "Data & privacy",
    title: "Cookie policy",
    description:
      "A direct explanation of the authentication and request-protection cookies used by the current application, without an invented consent or advertising layer.",
    current: "legal",
    documentStatus: "Initial implementation notice",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "Cookie names and lifetimes should be verified against the deployed environment. Jurisdiction-specific consent language and the company privacy contact still require legal review.",
    sections: [
      {
        id: "necessary-cookies",
        title: "Strictly necessary cookies",
        paragraphs: [
          "The authenticated application uses cookies needed to sign users in, refresh a session, protect sensitive requests, and complete identity-provider flows. Blocking them can prevent account access or connected sign-in from working.",
        ],
        bullets: [
          "session_token: an HttpOnly cookie used to authenticate a browser session.",
          "refresh_token: an HttpOnly cookie used to renew an eligible session.",
          "csrf_token: a request-protection token checked on unsafe cookie-authenticated requests.",
          "Temporary OAuth or verification cookies: short-lived state, verifier, MFA, or phone-verification values used to complete a requested security flow.",
        ],
      },
      {
        id: "browser-storage",
        title: "Related browser storage",
        paragraphs: [
          "The frontend uses session storage for temporary CSRF bootstrap state and pending OAuth-flow markers. Session storage is separate from cookies and is cleared with the browser session or by the application flow.",
          "The current authentication implementation does not place browser session or refresh tokens in local storage.",
        ],
      },
      {
        id: "analytics",
        title: "Analytics and advertising",
        paragraphs: [
          "The current repository does not include a public advertising network or cross-site analytics-cookie integration. This page must be updated, and consent added where required, before optional analytics or marketing cookies are introduced.",
        ],
      },
      {
        id: "controls",
        title: "Your controls",
        paragraphs: [
          "You can remove or block cookies through browser settings. Doing so may sign you out, prevent CSRF-protected actions, or interrupt GitHub, Google, MFA, and verification flows.",
          "ZeroOps AI does not currently expose a cookie-preference panel because no optional cookie category is represented as active in the codebase.",
        ],
      },
      {
        id: "changes-contact",
        title: "Changes and contact",
        paragraphs: [
          "This notice should be revised when cookie purpose, provider, duration, or optional tracking behavior changes.",
          "Cookie and privacy contact: [privacy contact email — pending legal review].",
        ],
      },
    ],
  },
  status: {
    eyebrow: "Operations",
    title: "Service status",
    description:
      "A transparent placeholder for public incident communication. No synthetic green state is shown when no public status feed is connected.",
    current: "status",
    documentStatus: "Public status feed not connected",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "This page does not assert that ZeroOps AI or a connected customer application is operational. A verified status provider or health aggregation endpoint must be connected before live availability is published.",
    noticeTone: "caution",
    sections: [
      {
        id: "current-state",
        title: "Current public state",
        paragraphs: [
          "Public availability is currently unverified. The repository exposes backend and worker health paths for deployment operations, but this public page is not connected to an independent status source.",
          "Do not interpret the absence of a posted incident as proof that all systems are healthy.",
        ],
      },
      {
        id: "future-coverage",
        title: "Planned coverage",
        bullets: [
          "Public web application and authentication.",
          "Control-plane API and database connectivity.",
          "Repository and GitHub integration.",
          "Deployment queue and dedicated worker availability.",
          "Azure deployment operations and log delivery.",
        ],
        note:
          "Customer-deployed application health is project-specific and belongs in the authenticated monitoring workspace when data is available.",
      },
      {
        id: "incidents",
        title: "Incident communication",
        paragraphs: [
          "A production status service should publish confirmed impact, affected components, start time, mitigation progress, and resolution. It should distinguish a ZeroOps platform incident from a failure in a customer repository, Azure subscription, or deployed application.",
          "No public incident-subscription or historical uptime commitment is active on this placeholder page.",
        ],
      },
      {
        id: "diagnostics",
        title: "Authenticated diagnostics",
        paragraphs: [
          "Signed-in users can review their own deployment state, stored logs, and project monitoring data in the workspace. Empty data remains an empty state; it is not converted into a healthy signal.",
        ],
      },
      {
        id: "support",
        title: "Report a problem",
        paragraphs: [
          "Operational support channel: [support contact or status provider — pending configuration]. Do not post credentials, source code, or deployment secrets to a public incident channel.",
        ],
      },
    ],
  },
  docs: {
    eyebrow: "Documentation",
    title: "ZeroOps AI documentation",
    description:
      "A concise guide to the workflow that exists today: source intake, deterministic repository evidence, App Service plan approval, worker deployment, and data-backed operations.",
    current: "docs",
    documentStatus: "Initial product guide",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    sections: [
      {
        id: "quickstart",
        title: "Quickstart",
        bullets: [
          "Create an account and enter the authenticated workspace.",
          "Connect GitHub and choose a repository and branch for review and deployment, or upload a ZIP archive for analysis only.",
          "Review the detected application facts and required environment-variable names.",
          "Generate and inspect the Azure App Service infrastructure plan.",
          "Confirm the region, tier, estimated cost, and required Azure connection.",
          "Approve the plan, then explicitly start the deployment.",
          "Follow the queued worker stages and inspect stored logs or metrics when they are available.",
        ],
      },
      {
        id: "source-intake",
        title: "1. Choose source",
        paragraphs: [
          "GitHub intake lists repositories available to the connected account and lets you select a branch for the review-and-deploy workflow.",
          "ZIP uploads are analysis-only until durable worker-accessible source storage is configured. They are limited by archive type, compressed size, extracted size, file count, and compression ratio; keep generated artifacts and secret files out of the archive.",
        ],
      },
      {
        id: "analysis",
        title: "2. Review repository evidence",
        paragraphs: [
          "Repository inspection derives facts such as framework, language, runtime, package manager, build and start commands, exposed port, environment-variable names, and likely deployment requirements.",
          "A configured model can enrich the explanation, with deterministic local inspection as a fallback. The current analysis path is not a separate worker and does not replace dedicated security or compliance scanning.",
        ],
      },
      {
        id: "plan",
        title: "3. Review the infrastructure plan",
        paragraphs: [
          "The planner converts recorded source evidence into an understandable Azure plan rather than exposing Terraform as the primary interface. The current deployable target is Azure App Service.",
          "Review the region, service tier, supporting resources, estimated monthly cost, reasoning, and required connection state. Cost is an estimate and may differ from the Azure invoice.",
        ],
      },
      {
        id: "approval",
        title: "4. Approve deliberately",
        paragraphs: [
          "A deployment cannot start without an approved plan. If the plan changes, its revision increases and the approval is cleared.",
          "Approval records the decision boundary. Starting a deployment is a separate explicit action that queues the approved specification.",
        ],
      },
      {
        id: "deployment",
        title: "5. Follow the deployment worker",
        paragraphs: [
          "For GitHub-backed projects, the dedicated deployment worker claims queued jobs and runs Azure image-build and App Service deployment stages outside the FastAPI request process. It reports stage, status, logs, failure reason, and live URL when those values exist.",
          "The current worker does not execute Terraform plan or apply. Review the product plan and recorded Azure execution state in the main workflow.",
        ],
      },
      {
        id: "operations",
        title: "6. Use recorded operational data",
        paragraphs: [
          "Deployment logs are stored in the application database and exposed through the product workflow. Live WebSocket updates are best-effort; monitoring pages read project metrics from the API when records are present.",
          "No metrics means no metrics: the UI should show an empty state until a deployed application and the configured telemetry path provide data.",
        ],
      },
      {
        id: "boundaries",
        title: "Current product boundaries",
        bullets: [
          "Azure App Service is the current approved deployment target.",
          "GitHub-backed source is required for deployment; ZIP uploads are analysis-only until durable shared source storage is configured.",
          "A dedicated Azure deployment worker is implemented; Terraform execution and separate analysis, security, monitoring, CI/CD, and remediation workers are not represented as live.",
          "Security status and monitoring are API-backed views, not compliance evidence.",
          "No automatic code modification or high-risk remediation should be assumed from analysis output.",
          "Public support, status, legal, and DPA channels remain initial placeholders until their operators and addresses are configured.",
        ],
      },
    ],
  },
  contact: {
    eyebrow: "Contact",
    title: "Contact ZeroOps AI",
    description:
      "Routing guidance for product, account, privacy, legal, and security questions while formal public support channels are being finalized.",
    current: "contact",
    documentStatus: "Public intake channels pending",
    lastUpdated: PUBLIC_CONTENT_UPDATED,
    notice:
      "No verified public inbox or support form is configured in this repository. The placeholders below must be replaced with monitored channels before production launch.",
    noticeTone: "caution",
    sections: [
      {
        id: "product-support",
        title: "Product and account support",
        paragraphs: [
          "Support contact: [support email or ticket portal — pending configuration]. Existing users should include the affected project name, approximate time, and the action they were attempting.",
          "Never include passwords, access tokens, secret values, private keys, full environment files, or private source code in an initial support request.",
        ],
      },
      {
        id: "security",
        title: "Security reports",
        paragraphs: [
          "Security contact: [security contact email — pending configuration]. Review the responsible-disclosure page before testing or sending a report.",
          "Do not submit sensitive exploit details until the address is verified and monitored.",
        ],
      },
      {
        id: "privacy",
        title: "Privacy and data requests",
        paragraphs: [
          "Privacy contact: [privacy contact email — pending legal review]. A production request flow must verify the requester before disclosing, changing, exporting, or deleting account data.",
        ],
      },
      {
        id: "legal",
        title: "Legal and contracting",
        paragraphs: [
          "Legal contact: [legal contact email — pending legal review]. Company legal name, registered address, governing jurisdiction, DPA request process, and procurement details remain to be completed.",
        ],
      },
      {
        id: "incident",
        title: "Service incidents",
        paragraphs: [
          "Status and incident channel: [status provider or operations contact — pending configuration]. The current public status page does not provide a live health assertion.",
        ],
      },
      {
        id: "useful-details",
        title: "Useful non-sensitive details",
        bullets: [
          "The page or workflow where the problem occurred.",
          "A project or deployment identifier, if it does not expose confidential information.",
          "The approximate time and time zone.",
          "The expected and observed result.",
          "A redacted error message or screenshot.",
        ],
      },
    ],
  },
} satisfies Record<string, PolicyPageProps>;
