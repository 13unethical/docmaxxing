
/* =========================================================
   CONFIG — all names, groups, descriptions, routes, badges,
   prices and mock data live here. Edit this, not the markup.
   ========================================================= */
const CONFIG = {
  brand: 'DocMaxxing',
  defaultRoute: 'home',
  signupCredits: 50,
  wordLimit: 5000,
  pricePlaceholder: '[N] credits',          // replace with real prices per tool below
  freeNote: 'Formatting and Work Review are free',
  // Veil page (menu → Information → Veil). Copy from the Veil design canvas.
  veil: {
    price: 2200, days: 30,                    // credits for 30 days of access, no auto-renewal (from the server)
    zipUrl: '/veil/download',                 // needs an active pass
    extensionsUrl: 'chrome://extensions',
    headline: 'Study help that stays on the page',
    shortcuts: [
      { key: 'Q', demo: 'ask', title: 'Ask about anything you select',
        text: 'A question, a paragraph, a task. Veil pastes it into the panel and explains it in plain words. Ask follow-ups right there.' },
      { key: 'S', demo: 'crop', title: 'Crop formulas and diagrams',
        text: 'Can’t select it? Drag a box around a formula, chart or slide. Veil reads the picture and solves it step by step.' },
      { key: 'H', demo: 'humanize', title: 'Humanize right where you write',
        text: 'Select your text in Google Docs or any text box. Veil rewrites it to sound natural and puts it back in place. No copy-paste.' },
    ],
    faq: [
      ['Why do I install it from a .zip file?', 'Veil isn’t in the Chrome Web Store yet, so you add it yourself through Developer mode. It takes about 3 minutes, and you only do it once.'],
      ['What happens when my {days} days end?', 'Veil stops answering until you renew. The extension stays installed. Renewing early adds {days} days on top of the time you have left.'],
      ['Do questions cost extra credits?', 'No. The {price} credits cover every question you ask during your {days} days.'],
      ['I use a Mac. Which keys do I press?', 'Use Option instead of Alt: Option+Q to ask, Option+S to crop, Option+H to humanize.'],
      ['Where does Veil work?', 'On any page you open in Chrome — Canvas, Blackboard, Google Docs, Quizlet, Wikipedia and PDFs opened in the browser.'],
    ],
  },

  home: {
    id: 'home', label: 'Dashboard', route: 'home', icon: 'home',
    description: 'Your credits, recent documents and all tools',
  },

  groups: [
    {
      id: 'check', label: 'Check & improve',
      items: [
        { id: 'turnitin', label: 'AI Detector', title: 'AI Detector', route: 'turnitin', icon: 'scan', primary: true,
          price: '[N] credits',
          description: 'Check your text for AI-generated content and plagiarism' },
        { id: 'humanizer', label: 'Humanizer', route: 'humanizer', icon: 'sparkles', primary: true,
          badge: '-50%', price: '[N] credits', guestPrice: 'Free for short texts',
          description: 'Rewrite text so it sounds natural and human' },
      ],
    },
    {
      id: 'write', label: 'Write',
      items: [
        { id: 'assignment', label: 'Assignment', route: 'assignment', icon: 'book', price: '[N] credits',
          description: 'Get help with your assignment in a chat' },
        { id: 'workspace', label: 'Editor', route: 'workspace', icon: 'file', price: '[N] credits',
          description: 'Write and edit documents' },
        { id: 'presentation', label: 'Slides', route: 'presentation', icon: 'slides', price: '[N] credits',
          description: 'Create presentations' },
      ],
    },
    {
      id: 'review', label: 'Format & review',
      items: [
        { id: 'format', label: 'Formatting', route: 'format', icon: 'align', free: true,
          description: 'Format your document in Harvard, APA and other styles' },
        { id: 'check', label: 'Work Review', route: 'check', icon: 'clipboard', free: true,
          description: 'See how well your work meets the task' },
      ],
    },
    {
      id: 'info', label: 'Information', info: true,
      items: [
        { id: 'veil', label: 'Veil', route: 'veil', icon: 'chrome', info: true,
          badge: 'NEW', tag: 'Extension',
          description: 'Study help in any tab — a Chrome extension' },
        { id: 'earn', label: 'Earn & Share', route: 'earn', icon: 'gift', info: true, free: true,
          description: 'Invite friends, earn 40% cashback, and unlock premium tools' },
        { id: 'tutorials', label: 'Tutorials', dialog: 'tutorials', icon: 'video', info: true, free: true,
          description: 'Short guided tours of every tool' },
        { id: 'help', label: 'Help', route: 'help', icon: 'info', info: true, free: true,
          description: 'Questions about your account, credits or payments' },
      ],
    },
  ],

  // Video tutorials dialog (menu → Tutorials). youtubeId: the part after "watch?v=" in a YouTube link.
  // Empty id = "video coming soon" placeholder. `tour` adds a button that starts the in-app tour.
  tutorials: {
    title: 'Video tutorials',
    items: [
      { id: 'start',     label: 'Getting started', youtubeId: '', description: 'Learn the basics: credits, history and where each tool lives.' },
      { id: 'turnitin',  label: 'AI Detector',  youtubeId: '', tour: 'scan',       description: 'Upload a file, read the AI and plagiarism score and see which parts look AI.' },
      { id: 'humanizer', label: 'Humanizer',    youtubeId: '', tour: 'humanizer',  description: 'Rewrite text so it sounds natural, then check it for AI in one click.' },
      { id: 'assignment',label: 'Assignment',   youtubeId: '', tour: 'assignment', description: 'Send your brief, confirm the requirements and get a draft in a chat.' },
      { id: 'workspace', label: 'Editor',       youtubeId: '', tour: 'editor',     description: 'Edit your document, humanize a selection and review suggested changes.' },
      { id: 'presentation', label: 'Slides',    youtubeId: '', tour: 'slides',     description: 'Turn a topic or your paper into a presentation and pick a template.' },
      { id: 'format',    label: 'Formatting',   youtubeId: '', tour: 'format',     description: 'Apply APA, MLA, Harvard and other styles to your document for free.' },
      { id: 'check',     label: 'Work Review',  youtubeId: '', tour: 'review',     description: 'See how well your work meets the brief and what to fix before you submit.' },
      { id: 'veil',      label: 'Veil extension', youtubeId: '',                  description: 'Check and humanize text right in your browser.' },
    ],
  },

  // Help page (menu → Information → Help): contact form + the site footer at the bottom.
  // Footer links and contacts are the same as on docmaxxing.com.
  help: {
    formTitle: 'Write to us',
    formLead: 'Tell us what happened. We usually reply within a few hours on working days.',
    topics: ['Account and sign-in', 'Credits and payments', 'Something does not work', 'Feature idea', 'Other'],
    sentToast: 'Message sent. We will reply to your email.',
    site: 'https://docmaxxing.com',
    email: 'support@docmaxxing.com',
    phone: '+998 99 077 99 09',
    hours: 'Monday–Friday, 9:00 AM–6:00 PM (GMT+5)',
    footer: {
      product: [
        { label: 'AI Humanizer', route: 'humanizer' },
        { label: 'Formatter', route: 'format' },
        { label: 'Assignments', route: 'assignment' },
        { label: 'Pricing', route: 'pricing' },
      ],
      links: [
        { label: 'Account', path: '/account-info' }, { label: 'Credits', path: '/credits' }, { label: 'About Us', path: '/about' },
        { label: 'Privacy Policy', path: '/privacy' }, { label: 'Terms and Conditions', path: '/terms' }, { label: 'Disclaimer', path: '/disclaimer' },
        { label: 'Payment Policy', path: '/payment-policy' }, { label: 'Delivery Policy', path: '/delivery-policy' },
        { label: 'Refund Policy', path: '/refund-policy' }, { label: 'Contact', path: '/contact' },
        { label: 'FAQ', path: '/faq' }, { label: 'Changelog', path: '/changelog' },
      ],
      socials: [
        { label: 'Email', icon: 'mail', url: 'mailto:support@docmaxxing.com' },
        { label: 'Telegram', icon: 'telegram', url: 'https://t.me/docmaxxing' },
        { label: 'WhatsApp', icon: 'whatsapp', url: 'https://wa.me/998990779909' },
        { label: 'Instagram', icon: 'instagram', url: 'https://www.instagram.com/doc.maxxing' },
        { label: 'YouTube', icon: 'youtube', url: 'https://www.youtube.com/@docmaxxing' },
        { label: 'X', icon: 'xlogo', url: 'https://x.com/docmaxxing' },
        { label: 'TikTok', icon: 'tiktok', url: 'https://www.tiktok.com/@docmaxxing' },
      ],
      copyright: '© 2026 DocMaxxing. Academic formatting, humanizing, and integrity tools.',
    },
  },

  // Earn & Share: referral program, same rules as docmaxxing.com/earn. MOCK numbers for the prototype.
  earn: {
    linkBase: 'https://docmaxxing.com/register?ref=',
    code: 'DMVMRFLV6U',
    giveCredits: 100, cashbackPct: 40, convertBonus: 1.2,
    creditsPerDollar: 40,          // MOCK: rate used for "Convert to credits" before the 1.2× bonus
    minWithdraw: 50, qualifyDeposit: 10,
    balance: 18.4,                 // MOCK wallet balance, $
    freeTurnitin: 1,
    milestones: [
      { friends: 1, reward: 'Free Turnitin' },
      { friends: 3, reward: '1,000 credits' },
      { friends: 5, reward: '3,000 credits' },
      { friends: 10, reward: 'Pro status' },
    ],
    share: [
      { label: 'Telegram', icon: 'telegram', url: 'https://t.me/share/url?url={link}&text={text}' },
      { label: 'WhatsApp', icon: 'whatsapp', url: 'https://wa.me/?text={text}%20{link}' },
      { label: 'X', icon: 'xlogo', url: 'https://x.com/intent/post?text={text}&url={link}' },
      { label: 'Email', icon: 'mail', url: 'mailto:?subject=DocMaxxing&body={text}%20{link}' },
    ],
    shareText: 'Get 100 free credits on DocMaxxing',
    // IDs only, no emails. deposits: [date, amount $]
    referrals: [
      { id: 'U-48213', joined: '2026-10-02', deposits: [['2026-10-02', 19], ['2026-10-16', 9]] },
      { id: 'U-51907', joined: '2026-10-09', deposits: [['2026-10-10', 18]] },
      { id: 'U-55340', joined: '2026-10-18', deposits: [] },
    ],
  },

  // Information pages (linked from the Help footer): policies, Credits, About, FAQ, Changelog.
  // Text copied from docmaxxing.com. Sections: p (paragraphs), list, after, qa ([question, answer]), related (page ids).
  // Side menu order; 'account' and 'contact' open the Account and Help pages.
  infoNav: ['account', 'credits', 'about', 'privacy', 'terms', 'disclaimer', 'payment-policy', 'delivery-policy', 'refund-policy', 'contact', 'faq', 'changelog'],
  // A list item "Term — text" shows the term in bold.
  legal: [
    {
      "id": "privacy",
      "title": "Privacy Policy",
      "lead": "How DocMaxxing collects, uses, and protects your data.",
      "sections": [
        {
          "h": "1. What we collect",
          "list": [
            "Account data — email, display name, password hash, account identifiers, and referral fields (referral code, referrer link, referral balance, milestone flags).",
            "Usage data — feature actions, credit balance changes, project metadata, job logs needed to run the product.",
            "Content you submit — briefs, drafts, uploads (PDF/DOCX/TXT/images), and generated outputs stored for your projects.",
            "Payment metadata — processed by Lemon Squeezy (we do not store full card numbers on DocMaxxing servers).",
            "Withdrawal details — wallet / payment details you submit for Earn & Share cashouts, plus request status.",
            "Support messages — what you send through the in-app support chat or WhatsApp / email."
          ]
        },
        {
          "h": "2. How we use data",
          "list": [
            "Deliver Format, Humanizer, Turnitin, Assignment, and Earn & Share features (and future tools when they leave Soon).",
            "Authenticate you, protect accounts, prevent abuse, and refund failed paid actions.",
            "Attribute referrals, calculate cashback, and process withdrawal requests.",
            "Improve reliability (for example diagnosing failed packaging or humanizer sessions).",
            "Communicate about account, billing, and support requests."
          ]
        },
        {
          "h": "3. Processors & third parties",
          "p": [
            "Depending on the feature, content may be processed by LLM / humanizer / detection providers (for example Claude, Gemini, StealthWriter, ZeroGPT) solely to complete the action you requested. Payments go through Lemon Squeezy."
          ]
        },
        {
          "h": "4. Retention",
          "p": [
            "We keep operational records as needed for security, fraud prevention, support, and legal compliance. You may request access or deletion of account data; some records may be retained where law or payment rules require it."
          ]
        },
        {
          "h": "5. Your choices",
          "list": [
            "Update profile details from Account (signed-in users).",
            "Manage referral activity from Earn & Share.",
            "Request data access or deletion via Contact.",
            "Stop using the service and close your account by contacting support."
          ]
        },
        {
          "h": "6. Security",
          "p": [
            "We use industry-standard protections for accounts and storage. No method of transmission or storage is 100% secure; please use a strong unique password."
          ]
        },
        {
          "h": "7. Contact",
          "contact": "Privacy questions:"
        }
      ],
      "updated": "Last updated: 3 August 2026."
    },
    {
      "id": "terms",
      "title": "Terms and Conditions",
      "lead": "The rules for using DocMaxxing.",
      "sections": [
        {
          "h": "1. Agreement",
          "p": [
            "By creating an account or using DocMaxxing you agree to these Terms and Conditions, our Privacy Policy, and related policies linked in the footer. If you do not agree, do not use the service."
          ]
        },
        {
          "h": "2. The service",
          "p": [
            "DocMaxxing provides academic document tools, including:"
          ],
          "list": [
            "Document formatting and style presets (free Format tool)",
            "Text humanization and AI-oriented detection helpers",
            "Citation helpers and Turnitin-style report workflows",
            "Assignment pipeline (research, writing, humanize, format, validation, delivery)",
            "Earn & Share referral cashback, milestones, credit conversion, and withdrawals"
          ],
          "after": [
            "Some menu items (Academic Check, Workspace, Presentation) may be listed as Soon and unavailable until launch. Features, pricing, and credit costs may change. Continued use after changes means you accept the updated terms."
          ]
        },
        {
          "h": "3. Accounts",
          "list": [
            "You must provide accurate registration details and keep credentials secure.",
            "You are responsible for activity under your account, including referrals attributed to your code.",
            "We may suspend accounts for abuse, chargebacks, referral fraud, or academic-misconduct facilitation beyond the product’s intended assistive use."
          ]
        },
        {
          "h": "4. Credits & payments",
          "p": [
            "Paid actions consume credits. Credit packages are purchased through Lemon Squeezy on the Credits page. You must be registered to buy. See also Payment Policy and Refund Policy."
          ]
        },
        {
          "h": "5. Earn & Share",
          "list": [
            "Cashback rates, qualifying deposit thresholds, milestones, conversion multipliers, and withdrawal minimums are described on Earn & Share and may change.",
            "Self-referral, fake deposits, or other abuse can void rewards and lead to suspension.",
            "Withdrawal requests reserve balance immediately and are subject to manual review."
          ]
        },
        {
          "h": "6. Your content & academic integrity",
          "list": [
            "You own the content you upload and remain responsible for submissions to your institution.",
            "DocMaxxing is an assistive tool. It does not guarantee grades, originality scores, or acceptance by universities.",
            "You must follow your institution’s academic integrity rules. Do not use the product to misrepresent authorship where forbidden."
          ]
        },
        {
          "h": "7. Acceptable use",
          "p": [
            "You agree not to:"
          ],
          "list": [
            "Attack, scrape abusively, or reverse-engineer the service beyond normal use",
            "Share accounts for commercial resale without permission",
            "Upload unlawful or harmful material",
            "Attempt to bypass credit metering, payment systems, or referral rules"
          ]
        },
        {
          "h": "8. Intellectual property",
          "p": [
            "DocMaxxing branding, UI, and software remain our property. Your uploaded documents remain yours. Generated outputs are licensed to you for personal academic use subject to these terms."
          ]
        },
        {
          "h": "9. Limitation of liability",
          "p": [
            "To the maximum extent permitted by law, DocMaxxing is provided “as is”. We are not liable for lost grades, rejected submissions, detection false positives/negatives, or third-party provider outages. See Disclaimer."
          ]
        },
        {
          "h": "10. Contact",
          "contact": ""
        }
      ],
      "updated": "Last updated: 3 August 2026."
    },
    {
      "id": "disclaimer",
      "title": "Disclaimer",
      "lead": "Important limits of DocMaxxing outputs and third-party checks.",
      "sections": [
        {
          "h": "Not a substitute for your judgement",
          "p": [
            "DocMaxxing is a productivity aid for formatting, drafting assistance, humanization, and integrity tooling. It is not a guarantee of academic success, originality, or compliance with any specific university policy."
          ]
        },
        {
          "h": "AI & detection scores",
          "list": [
            "Humanizer and LLM writers can change tone and wording; meaning should always be reviewed by you.",
            "AI detection scores (ZeroGPT, Turnitin-style reports, or others) can produce false positives and false negatives.",
            "A low score inside DocMaxxing does not guarantee a low score on your institution’s detector."
          ]
        },
        {
          "h": "Assignment pipeline",
          "p": [
            "Automatic research, writing, revision, grade-gate repairs, and packaging aim to follow your brief (sections, ±10% word budgets, rubric signals). Briefs vary; always proofread the final DOCX/ZIP before submission. Soft-export may still package a file when some soft checks fail — review warnings."
          ]
        },
        {
          "h": "Formatting",
          "p": [
            "Style presets (Harvard, APA, MLA, custom) approximate common rules. Institutions sometimes require local variants. Verify fonts, margins, spacing, headings, and reference style against your brief."
          ]
        },
        {
          "h": "Soon features",
          "p": [
            "Academic Check, Workspace, and Presentation may appear in navigation but are not live until launched. Do not rely on them for deadlines while they show the Soon page."
          ]
        },
        {
          "h": "Referrals & rewards",
          "p": [
            "Earn & Share cashback, milestones, Pro discounts, and withdrawals depend on successful referred deposits and manual withdrawal review. Program terms can change; abuse voids rewards."
          ]
        },
        {
          "h": "Third-party services",
          "p": [
            "Features depend on external providers (LLMs, StealthWriter, ZeroGPT, Lemon Squeezy, browser automation). Outages, model changes, or provider policy updates can affect results and payouts."
          ]
        },
        {
          "h": "No professional advice",
          "p": [
            "Nothing on DocMaxxing is legal, academic, or professional advice. If in doubt, ask your lecturer or institution."
          ]
        }
      ],
      "updated": "Last updated: 3 August 2026."
    },
    {
      "id": "payment-policy",
      "title": "Payment Policy",
      "lead": "How credit purchases and Assignment payments work on DocMaxxing.",
      "sections": [
        {
          "h": "1. Who can pay",
          "p": [
            "You must create a DocMaxxing account before buying credits. Guests can view the Credits page, but checkout requires registration / sign-in."
          ]
        },
        {
          "h": "2. What you pay for",
          "list": [
            "Credit packages — prepaid balance for Humanize, Turnitin, Assignment, and other live metered actions.",
            "Assignment projects — priced per project after brief analysis (shown before you confirm payment from your credit balance).",
            "Free tools — Format does not require credits.",
            "Not billable yet — Academic Check, Workspace, and Presentation are Soon and cannot be charged until they launch."
          ]
        },
        {
          "h": "3. Processors",
          "p": [
            "DocMaxxing checkout is processed by Lemon Squeezy (merchant of record for card / wallet payments).",
            "DocMaxxing does not store full payment card numbers. Crypto wallet details you submit for Earn & Share withdrawals are used only to process payout requests."
          ]
        },
        {
          "h": "4. Prices & currency",
          "p": [
            "Package prices are shown on the Credits page (for example Starter $9 / 1,000 credits and Pro $20 / 2,500 credits). Exchange rate for metering is typically $1 = 100 credits. Custom / volume deals are arranged via sales on WhatsApp. Taxes or local fees may apply depending on your region and processor rules."
          ]
        },
        {
          "h": "5. When credits appear",
          "p": [
            "After a successful Lemon Squeezy payment confirmation, credits are added to your account balance. If payment succeeds but balance does not update within a short time, contact support with your account email and the Lemon Squeezy order id."
          ]
        },
        {
          "h": "6. Referral cashback (not a purchase)",
          "p": [
            "Referral balances earned via Earn & Share are separate from purchased credits. You may convert referral USD to credits (1.2× bonus) or request a withdrawal (minimum $50). Withdrawals are reviewed manually."
          ]
        },
        {
          "h": "7. Failed paid actions",
          "p": [
            "If a paid feature fails on our side after credits were charged, we refund those credits to your balance whenever automatic recovery is possible."
          ]
        },
        {
          "h": "8. Chargebacks",
          "p": [
            "Unjustified chargebacks may lead to account suspension and forfeiture of remaining credits. Contact us first so we can resolve billing issues quickly."
          ]
        },
        {
          "h": "9. Related policies",
          "related": [
            "refund-policy",
            "delivery-policy",
            "terms",
            "credits"
          ]
        }
      ],
      "updated": "Last updated: 3 August 2026."
    },
    {
      "id": "delivery-policy",
      "title": "Delivery Policy",
      "lead": "How digital outputs are delivered after you run a DocMaxxing feature.",
      "sections": [
        {
          "h": "1. Instant digital delivery",
          "p": [
            "DocMaxxing delivers digital products inside the product UI — not by post. When an action completes, your file or report is available to download immediately from the relevant page."
          ]
        },
        {
          "h": "2. What gets delivered",
          "list": [
            "Format — formatted DOCX download after processing.",
            "Humanizer — rewritten text in the editor / session output.",
            "Turnitin — similarity / AI / highlights reports when generated successfully.",
            "Assignment — a delivery ZIP (formatted document + supporting package files) via Download assignment once packaging finishes.",
            "Earn & Share — referral rewards appear as credits, free Turnitin reports, Pro status, or pending withdrawal requests (not file downloads)."
          ],
          "after": [
            "Academic Check, Workspace, and Presentation are currently Soon and do not deliver outputs yet."
          ]
        },
        {
          "h": "3. Assignment packaging",
          "p": [
            "The Assignment pipeline packages only after prior stages complete (including humanize, format, review/detection as configured). If packaging was interrupted, use Download again — the app can rebuild the ZIP. Soft-export may allow download even when some soft validation warnings remain; always open and review the DOCX before submitting to your university."
          ]
        },
        {
          "h": "4. Delivery time",
          "list": [
            "Most Format jobs: seconds to a few minutes.",
            "Humanizer batches: depends on StealthWriter queue and document length.",
            "Turnitin reports: depends on provider queue.",
            "Full Assignment runs: typically several minutes depending on section count, LLM calls, and detection.",
            "Referral withdrawals: manual review — timing depends on support hours and payment rails."
          ]
        },
        {
          "h": "5. Failed delivery",
          "p": [
            "If a paid action fails before you receive usable output, credits for that action are refunded when possible. For Assignment ZIP issues, contact support with your project id from the URL."
          ]
        },
        {
          "h": "6. Retention",
          "p": [
            "Project files are stored so you can reopen and re-download while the project remains on the account. Do not rely on DocMaxxing as the only backup — keep your own copies of final submissions."
          ]
        }
      ],
      "updated": "Last updated: 3 August 2026."
    },
    {
      "id": "refund-policy",
      "title": "Refund Policy",
      "lead": "All purchases are final.",
      "sections": [
        {
          "h": "1. All sales are final",
          "p": [
            "Plans (Basic, Pro, Max), pay-as-you-go credits, and Assignment payments are digital goods that are delivered to your account immediately after payment. We do not offer refunds, including for unused or partially used credits and for the unused part of a plan period.",
            "By completing checkout you ask us to deliver the digital content immediately and acknowledge that you lose any statutory right of withdrawal once delivery has started. Nothing in this policy limits rights you have under mandatory consumer law."
          ]
        },
        {
          "h": "2. Subscriptions and cancellation",
          "p": [
            "Plans renew every month until you cancel. You can cancel at any time from Billing → Manage subscription. Cancelling stops future renewals; your plan and the credits you already received stay active until the end of the period you paid for. Past payments are not refunded, in full or in part."
          ]
        },
        {
          "h": "3. Failed paid actions",
          "p": [
            "If a paid action fails on our side (provider error, crash after debit, failed packaging with no usable output), the credits charged for it are returned to your DocMaxxing balance automatically. These are credit returns to your balance, not cash refunds."
          ]
        },
        {
          "h": "4. Billing errors",
          "p": [
            "If you were charged twice for the same purchase, or paid and did not receive your plan or credits, contact us with your Lemon Squeezy order id. We will deliver what you paid for or reverse the duplicate charge."
          ]
        },
        {
          "h": "5. Referral balances & withdrawals",
          "p": [
            "Referral cashback is not a credit purchase. Converting referral USD to credits is final for that amount. Withdrawal requests reserve funds immediately; if a request is rejected by admin, the reserved USD is returned to your referral balance. Approved withdrawals are not refundable as platform credits."
          ]
        },
        {
          "h": "6. Chargebacks",
          "p": [
            "Please contact us before filing a chargeback. Chargebacks on delivered purchases may result in account suspension and loss of remaining credits and plan access."
          ]
        },
        {
          "h": "7. Contact",
          "contact": "Email or WhatsApp us (Monday–Friday, 9:00 AM–6:00 PM GMT+5):"
        }
      ],
      "updated": "Last updated: 27 October 2026."
    },
  {
    "id": "credits",
    "title": "Credits",
    "lead": "Credits power paid DocMaxxing tools. Buy once, spend only when you run a paid action.",
    "sections": [
      {
        "h": "How credits work",
        "p": [
          "Your balance sits on your account. Format stays free and does not spend credits. Humanize, Turnitin, Assignment projects, and other metered actions do. Rate: $1 = 100 credits (1 credit ≈ $0.01). Failed jobs that never complete are refunded to your balance when automatic recovery runs.",
          "New accounts receive a welcome bonus of 50 credits. If you sign up with a friend’s referral link, you also get +100 referral signup credits."
        ]
      },
      {
        "h": "What each action costs",
        "list": [
          "Humanize — 25 credits per call",
          "AI detect — 1 credit per 100 words (minimum 1)",
          "Citation insert — 2 credits each time you insert a citation or add a reference",
          "Turnitin check — 300 credits",
          "Assignment projects — priced per brief (word count, priority, extras) in USD, then charged as credits before the pipeline starts"
        ],
        "after": [
          "Academic Check, Workspace, and Presentation are currently marked Soon in the app — they are not available to run yet even if older docs mentioned credit prices for them.",
          "Users with Pro (unlocked via Earn & Share milestones) get a persistent 10% discount on paid feature charges. Free Turnitin report rewards can cover a Turnitin run at zero credit cost."
        ]
      },
      {
        "h": "Packages",
        "list": [
          "Starter — 1,000 credits for $10",
          "Pro pack — 2,200 credits for $20 (most popular)",
          "Custom / teams — contact sales via WhatsApp or support email"
        ],
        "after": [
          "Checkout is handled by Lemon Squeezy (cards and wallets). You need a DocMaxxing account before buying; guests who click Buy are asked to register first."
        ]
      },
      {
        "h": "Earn credits without buying",
        "list": [
          "Share your referral link — friends get +100 credits on signup",
          "You earn 40% cashback (USD) on their deposits into your referral balance",
          "Convert referral USD to credits at a 1.2× bonus rate, or withdraw from $50+"
        ],
        "after": [
          "Full details live on the Earn & Share page (signed-in)."
        ]
      },
      {
        "h": "Seeing your balance",
        "p": [
          "The Credits pill in the header shows your current balance when you are signed in. Payment receipts come from Lemon Squeezy; support can look up ledger entries if something looks wrong."
        ]
      },
      {
        "h": "Related",
        "related": [
          "pricing",
          "earn",
          "payment-policy",
          "refund-policy",
          "faq"
        ]
      }
    ],
    "updated": ""
  },
  {
    "id": "about",
    "title": "About Us",
    "lead": "DocMaxxing is an academic document studio for formatting, humanizing, integrity checks, and assignment delivery.",
    "sections": [
      {
        "h": "",
        "p": [
          "DocMaxxing helps students and researchers ship clean academic documents without fighting Word styles for hours. The product combines free formatting, AI humanization, Turnitin-style reports, citations, a full Assignment pipeline, and a referral cashback program in one place."
        ]
      },
      {
        "h": "What you can do today",
        "list": [
          "Format — paste or upload text, apply Harvard / APA / MLA presets, fonts, margins, cover page, references, and citations, then download a DOCX. Free.",
          "Humanizer — rewrite AI-sounding prose through StealthWriter (Legacy 5.1), including large batches up to ~5,000 words in Assignment.",
          "Turnitin — run similarity / AI-oriented report workflows billed in credits.",
          "Assignment — upload a brief, review the price, pay once, then auto-run research → blueprint → writing → citations → humanize → format → review → AI detection → delivery ZIP.",
          "Academic Check — compare a draft to your assignment brief and rubric (free).",
          "Earn & Share — invite friends, earn cashback on their deposits, unlock milestone rewards, convert to credits, or withdraw."
        ]
      },
      {
        "h": "Coming soon",
        "list": [
          "Workspace — in-editor paid tools",
          "Presentation — presentation helpers"
        ],
        "after": [
          "These items appear in the sidebar and open a “Soon” page until they launch."
        ]
      },
      {
        "h": "How Assignment works",
        "p": [
          "The Assignment pipeline treats your brief as the source of truth. We extract required sections, word budgets (±10%), formatting rules, rubric / learning outcomes, and mandatory evidence (for example lecture/seminar references in Learning Journals). Writing can happen section-by-section; humanizing runs on large batches; a grade gate repairs word count and rubric gaps before export."
        ]
      },
      {
        "h": "Credits economy",
        "p": [
          "Format stays free. Paid actions (humanize, Turnitin, Assignment, and related metered tools) spend credits. New accounts get 50 welcome credits. Packages are sold on the buy credits screen via Lemon Squeezy (see the Credits guide)."
        ]
      },
      {
        "h": "Who we are for",
        "p": [
          "Undergraduates, postgraduates, and anyone who needs consistent academic formatting and drafting help — especially when deadlines are tight and briefs are strict."
        ]
      }
    ],
    "updated": ""
  },
  {
    "id": "faq",
    "title": "FAQ",
    "lead": "Common questions about DocMaxxing tools, credits, referrals, and Assignment delivery.",
    "sections": [
      {
        "h": "Getting started",
        "qa": [
          [
            "Do I need an account?",
            "You can try Format as a guest for many flows. Buying credits, saving Assignment progress, running paid Humanizer / Turnitin actions, and Earn & Share require sign-up."
          ],
          [
            "Where do I buy credits?",
            "Read the Credits guide, then open Buy credits. Checkout uses Lemon Squeezy. Guests are asked to register before checkout."
          ],
          [
            "What are welcome credits?",
            "New accounts receive 50 welcome credits. Signing up with a referral link also grants +100 referral bonus credits."
          ]
        ]
      },
      {
        "h": "Format",
        "qa": [
          [
            "What files can I upload?",
            "Briefs and text as paste or DOC/PDF/TXT/images (as shown on the Format page)."
          ],
          [
            "Which styles are supported?",
            "Harvard, APA, MLA presets plus custom font, size, spacing, margins, cover page, references, and citations."
          ],
          [
            "Does Format cost credits?",
            "No — Format is free."
          ]
        ]
      },
      {
        "h": "Humanizer",
        "qa": [
          [
            "How does humanizing run?",
            "The standalone Humanizer and Assignment humanizing use StealthWriter Legacy 5.1. Assignment batches can run up to ~5,000 words."
          ],
          [
            "Why is AI score still high?",
            "Later revision / repair steps can rewrite prose. The pipeline re-humanizes after those steps; always re-check the final DOCX on your detector of choice."
          ],
          [
            "Cost?",
            "Typically 25 credits per humanize action (Pro users get 10% off paid charges)."
          ]
        ]
      },
      {
        "h": "Assignment",
        "qa": [
          [
            "What is the pipeline?",
            "Upload brief → price → pay → research → blueprint → write sections → citations → humanize → format → review/revision → validation → AI detection → delivery ZIP."
          ],
          [
            "Word count rules?",
            "Targets use a ±10% band (example: 1200 → 1080–1320). Overages are trimmed (including Gemini smart-trim when needed)."
          ],
          [
            "Download says ready but nothing downloads?",
            "Use Download again — packaging rebuilds the ZIP. Hard-refresh if the UI was stale."
          ]
        ]
      },
      {
        "h": "Turnitin & detection",
        "qa": [
          [
            "Is this official Turnitin?",
            "We provide Turnitin-style report workflows through configured providers. Institutional Turnitin portals can still differ."
          ],
          [
            "Cost?",
            "Typically 300 credits per check. Earn & Share milestones can award free detailed Turnitin reports."
          ]
        ]
      },
      {
        "h": "Academic Check",
        "qa": [
          [
            "What does it do?",
            "Paste your assignment brief and draft (or upload DOCX/PDF) to get a readiness score, missing requirements, and an action plan — free for everyone."
          ],
          [
            "Do I need credits?",
            "No — Academic Check does not spend credits."
          ]
        ]
      },
      {
        "h": "Earn & Share",
        "qa": [
          [
            "How does cashback work?",
            "When someone you referred deposits, you earn 40% of that USD amount into your referral balance."
          ],
          [
            "What counts as a qualifying friend?",
            "Their first deposit of $10+. Milestones unlock free Turnitin reports, bonus credits, and Pro (10% off) at 10 qualifying friends."
          ],
          [
            "Convert or withdraw?",
            "Convert referral USD to credits at 1.2×, or request a withdrawal from $50 minimum (manual review)."
          ]
        ]
      },
      {
        "h": "Coming soon",
        "qa": [
          [
            "What about Workspace and Presentation?",
            "They are listed in the menu but currently show a Soon page until they launch."
          ]
        ]
      },
      {
        "h": "Billing",
        "qa": [
          [
            "Who processes payment?",
            "Lemon Squeezy for card / wallet payments (merchant of record)."
          ],
          [
            "Refunds?",
            "All purchases are final and we do not offer refunds. You can cancel a plan at any time; it stays active until the end of the paid period. Credits for failed actions return to your balance automatically. See Refund Policy."
          ]
        ],
        "related": [
          "refund-policy"
        ]
      }
    ],
    "updated": ""
  },
  {
    "id": "changelog",
    "title": "Changelog",
    "lead": "Product updates for DocMaxxing. Newest first.",
    "sections": [
      {
        "h": "August 2026",
        "list": [
          "Earn & Share — referral links, 40% deposit cashback, qualifying milestones ($10+), convert at 1.2×, withdrawals from $50, admin approve/reject.",
          "Referral signup bonus: +100 credits for invited users; Pro status (10% off paid checks) at 10 qualifying referrals.",
          "Payment checkout: Lemon Squeezy (primary). Cryptomus / Gumroad / Paddle kept as emergency fallbacks in code only.",
          "Academic Check, Workspace, and Presentation temporarily gated behind the shared Soon page (code kept for later).",
          "Information hub redesigned: secondary pill menu + card content layout for Account, Credits, policies, FAQ, and Changelog."
        ]
      },
      {
        "h": "26 July 2026",
        "list": [
          "Dedicated information pages for Account, Credits, About, policies, Contact, FAQ, and Changelog.",
          "Site footer with policies + social icons for every account (guest and registered).",
          "Guest nav: Credits pill opens pricing (purchase still requires registration).",
          "Format accordion panels gained icons (Text, Layout, Advanced, Cover, References, Citations)."
        ]
      },
      {
        "h": "25–26 July 2026 — Assignment quality",
        "list": [
          "±10% hard word budgets (was ±5%); Gemini smart-trim when merge/total is slightly over.",
          "Humanizer batches up to ~5,000 words; heading-only passthrough fixed so body always humanizes.",
          "Re-humanize after Gemini revision / grade-gate rewrites that undid StealthWriter output.",
          "Heading normalization after providers collapse ## Title onto body text.",
          "Download UX: “ready” only when a package exists; project download endpoint rebuilds ZIP; soft-export if grade gate soft-fails."
        ]
      },
      {
        "h": "July 2026 — Grade-driven Learning Journal",
        "list": [
          "AssignmentSpec source of truth: sections, budgets, formatting, rubric, LOs, lecture/seminar refs.",
          "Rubric coverage analysis + predicted grade; validate → repair (max 5) loop.",
          "Writer prompts and expansion/trim aligned to section targets; delivery ships Format Engine DOCX."
        ]
      },
      {
        "h": "Earlier 2026",
        "list": [
          "Credits economy with package checkout (Starter / Pro / custom sales).",
          "Live tools suite: Format, Humanizer, Turnitin, Assignment (Check / Workspace / Presentation later).",
          "Admin analytics for credits sold/used and user activity."
        ]
      }
    ],
    "updated": ""
  }
  ],

  // Billing (Account settings → Billing). MOCK subscription; card and receipts live in Lemon Squeezy.
  billing: {
    plan: 'pro',                       // id from CONFIG.pricing.plans
    status: 'active',                  // 'active' | 'canceled' (runs until the period ends)
    renewsOn: '2026-11-24',
    card: { brand: 'Visa', last4: '4242', exp: '08/28' },
    history: [
      { date: '2026-10-24', item: 'Pro plan · monthly', amount: 19, status: 'Paid' },
      { date: '2026-09-24', item: 'Pro plan · monthly', amount: 19, status: 'Paid' },
      { date: '2026-09-02', item: '2,000 credits · one-time', amount: 52, status: 'Paid' },
      { date: '2026-08-24', item: 'Basic plan · monthly', amount: 9, status: 'Refunded' },
    ],
    processorNote: 'Payments are processed by Cryptomus. We never see or store your wallet keys.',
    lemonNote: 'Payments are processed by Lemon Squeezy, our merchant of record. We never see or store your card details.',
  },

  // Pages that are not in the menu (opened from buttons)
  extraItems: [
    { id: 'account', label: 'Account', route: 'account', icon: 'user', hidden: true,
      description: 'Manage your DocMaxxing profile, password, and access to paid tools' },
    { id: 'settings', label: 'Account settings', route: 'settings', icon: 'gear', hidden: true,
      description: 'Your profile details and password' },
    { id: 'billing', label: 'Billing', route: 'billing', icon: 'card', hidden: true,
      description: 'Your plan, payment method and payments' },
    ...['privacy', 'terms', 'disclaimer', 'payment-policy', 'delivery-policy', 'refund-policy', 'credits', 'about', 'faq', 'changelog'].map(id => ({
      id, route: id, legal: true, hidden: true, icon: 'file', label: '', description: '' })),
    { id: 'pricing', label: 'Pricing', route: 'pricing', icon: 'flash', hidden: true,
      description: 'Pick a plan or buy credits once' },
    { id: 'admin', label: 'Admin', route: 'admin', icon: 'shield', hidden: true, description: 'Users, credits, activity and service settings' },
    { id: 'admin-users', label: 'Users · Admin', route: 'admin-users', icon: 'users', hidden: true, description: '' },
    { id: 'admin-activity', label: 'Activity · Admin', route: 'admin-activity', icon: 'pulse', hidden: true, description: '' },
    { id: 'admin-settings', label: 'Settings · Admin', route: 'admin-settings', icon: 'sliders', hidden: true, description: '' },
  ],

  // Pricing page (Figma 179:1227). ok: false = not included (✕). value = amount on the right; hint = tooltip.
  // Credit equivalents follow the plans: 25 credits per Humanize run, 300 credits per Turnitin scan.
  pricing: {
    title: 'Choose your plan',
    subtitle: 'Credits for checks and humanizing, free generations every month and unlimited writing tools.',
    plans: [
      { id: 'basic', name: 'Basic', price: 9, tagline: 'For quick checks & formatting', cta: 'Get Basic',
        credits: 300, perks: ['= 12 Humanize runs', '= 1 Official Turnitin scan'],
        freeStyle: 'plain', unlimitedStyle: 'outline',
        free: [
          { label: 'Assignment Writer', value: '1 free paper' },
          { label: 'AI Presentation', value: '1 free presentation' },
          { label: 'Academic Check', value: '3 free checks' },
          { label: 'Official Turnitin Report', ok: false },
        ],
        unlimited: [
          { label: 'Veil Fast', ok: false, value: 'No unlimited' },
          { label: 'Veil Pro', ok: false, value: 'No unlimited' },
          { label: 'Workspace, Format & Citations', value: 'Unlimited' },
        ] },
      { id: 'pro', name: 'Pro', price: 19, tagline: 'For regular essays, checks and slides', cta: 'Get Pro',
        highlight: true, badges: [{ text: 'Most popular', kind: 'accent' }],
        credits: 1000, perks: ['= 40 Humanize runs', '= 3 Official Turnitin scans'],
        free: [
          { label: 'Humanizer (EN/RU)', value: '15 free / day' },
          { label: 'Assignment Writer', value: '3 free papers' },
          { label: 'AI Presentations', value: '5 free decks' },
          { label: 'Official Turnitin Report', ok: false },
        ],
        unlimited: [
          { label: 'Veil Fast', value: '30-day unlimited' },
          { label: 'Veil Pro', value: '7-day unlimited' },
          { label: '+ 4 unlimited tools', hint: 'Format, Academic Check, Citations, Workspace' },
        ] },
      { id: 'max', name: 'Max', sub: 'Exam pass', price: 39, tagline: 'Everything for exam season', cta: 'Get Max',
        badges: [{ text: '35% OFF', kind: 'green' }],
        credits: 2500, perks: ['= 100 extra Humanize runs', '= 8 Official Turnitin scans'],
        free: [
          { label: 'Humanizer (EN/RU)', value: '40 free / day' },
          { label: 'Assignment Writer', value: '8 free papers' },
          { label: 'AI Presentations', value: '15 free decks' },
          { label: 'Official Turnitin Report', value: '1 free scan' },
        ],
        unlimited: [
          { label: 'Veil Stealth', value: '30-day unlimited' },
          { label: 'Veil Deep', value: '30-day unlimited' },
          { label: '+ 4 unlimited tools', hint: 'Format, Academic Check, Citations, Workspace' },
          { label: 'Lowest cost per credit', value: '40% cheaper' },
        ] },
    ],
    // One-time credits: $2 base + $5 per 500-credit pack; equivalents use the same rates as the plans.
    payg: { title: 'Pay as you go', lead: 'No subscription. Buy credits once and use them whenever you need.',
      min: 500, max: 10000, step: 500, start: 2000, baseUsd: 2, usdPerStep: 5, creditsPerScan: 300, creditsPerRun: 25,
      badge: 'Credits never expire', cta: 'Buy credits' },
  },

  // App header (shown above every app page)
  header: {
    greeting: 'Welcome back, {name}',
    guestGreeting: 'Welcome to DocMaxxing',
    subtitle: 'Got a text ready? Check it for AI, then humanize it.',
    pricingLabel: 'See Pricing',
  },

  // Cross-links between the two main tools (shown under results)
  flows: {
    humanizer: { runLabel: 'Humanize', loadingLabel: 'Humanizing your text…', resultTitle: 'Humanized text',
                 next: { label: 'Check for AI', to: 'turnitin' } },
    turnitin:  { runLabel: 'Check text', loadingLabel: 'Checking for AI and plagiarism…', resultTitle: 'Check result',
                 next: { label: 'Humanize this text', to: 'humanizer', hint: 'High AI score? Rewrite it in a natural voice.' } },
  },

  user: {
    balance: 50, name: 'flieddi',
    usage: { used: 12, limit: 50, label: 'credits used this month' },   // progress bar under the balance
    id: '#103', email: 'flieddi@example.com',   // MOCK account data
    isAdmin: false,   // shows Admin in the menu
    minPassword: 6,
    // "Account information" block on the Account page (text from docmaxxing.com/account-info)
    info: {
      title: 'Account Information',
      lead: 'Manage your DocMaxxing profile, password, and access to paid tools.',
      unlocks: ['Credits purchases via Lemon Squeezy', 'Assignment pipeline saved progress and delivery ZIP downloads',
        'Humanizer & Turnitin credit-based paid runs', 'Earn & Share referral cashback, milestones, and withdrawals'],
      change: ['Display name', 'Password (current + new password)'],
      changeNote: 'Billing history lives with your payment provider receipts. Referral balance and milestones live on Earn & Share.',
      tips: ['Use a unique password (at least 6 characters)', 'Do not share login links or session cookies', 'Log out on shared computers'],
    },
    menu: [
      { label: 'Account settings', icon: 'gear', act: 'account' },
      { label: 'Billing', icon: 'card', act: 'billing' },
      { label: 'Admin panel', icon: 'shield', act: 'admin', admin: true },
      { label: 'Sign out', icon: 'logout', act: 'signout', danger: true },
    ],
  },

  // Home page
  homePage: {
    headings: { new: 'Let’s get you started', returning: 'Welcome back' },
    subtitle: 'Got a text ready? Check it for AI, then humanize it.',
    // MOCK credits per run, shown as "~5 credits" and used for "enough for ~N checks". Replace with real prices.
    estimates: { turnitin: 5, humanizer: 5, presentation: 30 },
    lowBalance: 10,                    // at or below this, the Top up button becomes the main action
    creditHistoryPreview: 3,           // operations shown before "Show more"
    recentCount: 3,                    // documents shown in History before "Show more"
    startTitle: 'Start here',
    // Shown on top of the dashboard after sign-up until the user hides it. The video is tutorials → "Getting started".
    introVideo: { title: 'New here? Watch how DocMaxxing works', text: 'A 2-minute overview: check a text for AI, humanize it, format it and keep track of credits.',
      cta: 'Watch the overview', more: 'All tutorials' },
    startPlaceholder: 'Paste your essay or report here…',
    titles: { credits: 'Credit history', guestCredits: 'Credits', history: 'History', tasks: 'What else do you need?' },
    historySub: 'Pick up where you left off.',
    tasks: [
      { tool: 'assignment',   hint: 'Write a full assignment from your brief and sources' },
      { tool: 'workspace',    hint: 'Edit and polish your draft with AI suggestions' },
      { tool: 'presentation', hint: 'Turn your paper into a presentation in minutes' },
      { tool: 'format',       hint: 'Apply APA, MLA, Harvard and other styles automatically' },
      { tool: 'check',        hint: 'Get feedback on structure, arguments and grammar' },
      { tool: 'veil',         hint: 'Check and humanize text right in your browser' },
    ],
  },

  // "Getting started" checklist on Home. A step is done when its tool is run
  // (or, for stub tools, opened). `account` is done when the user is signed in.
  // Credit history. amount: positive = added, 0 = free run, null = price placeholder ("−[N]")
  creditHistory: [
    { id: 'c1', label: 'Humanizer run',             tool: 'humanizer',    date: '2026-10-19', amount: null },
    { id: 'c2', label: 'AI Detector scan', tool: 'turnitin',     date: '2026-10-18', amount: null },
    { id: 'c3', label: 'Formatting (Harvard)',      tool: 'format',       date: '2026-10-16', amount: 0 },
    { id: 'c4', label: 'Assignment chat',           tool: 'assignment',   date: '2026-10-14', amount: null },
    { id: 'c5', label: 'Slides generated',          tool: 'presentation', date: '2026-10-11', amount: null },
    { id: 'c6', label: 'Sign-up bonus',                                   date: '2026-10-09', amount: 50 },
  ],

  // Assignment screen: one input (files + instructions) → parsed brief + price → chat
  // AI Detector checks whole documents (Turnitin-style). price = per document, placeholder for now.
  // Our own AI detector (the default mode on the AI Detector page): pasted text in, one AI % out. Files go to Turnitin.
  // Word limits and the daily allowance match /api/detector/free (FREE_DETECT_* on the server).
  detector: {
    minWords: 40,
    maxWords: 5000,
    guestMaxWords: 1500,
    switch: {
      quick:    { title: 'DocMaxxing Detector', sub: 'AI % in seconds' },
      turnitin: { title: 'Turnitin report',     sub: 'Official AI + similarity' },
    },
  },

  scan: {
    price: '[N] credits',
    formats: 'DOCX or PDF',
    maxFileSizeMb: '[N]',
    highlightsMinAi: 20,                 // at or below this AI score the next step is formatting, not humanizing
    lowAiHighlightsNote: 'Turnitin shows AI from 1 to 19% as *%. Downloads a PDF of your document with those parts highlighted.',
    // Levels: value < low → Low, value ≥ high → High, otherwise Medium
    levels: { ai: { low: 20, high: 50 }, similarity: { low: 15, high: 30 } },
    verdicts: {
      High:   { title: 'Likely AI-written', text: 'Most of this text looks AI-generated. The AI report shows which parts. Humanize the text before you submit.' },
      Medium: { title: 'Some parts may look AI-written', text: 'Part of this text looks AI-generated. The AI report shows which parts.' },
      Low:    { title: 'Looks human-written', text: 'We found little or no AI-generated text.' },
    },
    highSimilarityNote: 'Similarity is high: check your quotes and citations.',
    checkingNote: 'About 2 min left',
    failedNote: 'Check failed. Your credits were refunded.',
    sampleText: 'Online learning has changed the way many students experience university. It is important to note that recorded lectures and digital forums give learners more flexibility than ever before. A 2023 survey found that a majority of undergraduates now watch at least some lectures online. Furthermore, this shift raises questions about motivation, isolation and whether flexible study helps or harms deep understanding of complex topics.',
    // Previous checks for the "returning user" state. minutesAgo = relative to now.
    mockChecks: [
      { id: 's1', file: 'Road in Etten.pdf',                        status: 'checking', minutesAgo: 1 },
      { id: 's2', file: 'Article_Review.docx',                      status: 'done', ai: 91,  sim: 8,  minutesAgo: 11 },
      { id: 's3', file: 'International Law.docx',                   status: 'done', ai: 0,   sim: 31, date: '2026-10-16T22:40:00' },
      { id: 's4', file: 'Presidential Debate Analysis.docx',        status: 'done', ai: 100, sim: 3,  date: '2026-10-14T22:21:00' },
      { id: 's5', file: 'Article review.docx',                      status: 'done', ai: 0,   sim: 6,  date: '2026-10-14T20:48:00' },
      { id: 's6', file: 'The Developmental Model of Learning.docx', status: 'done', ai: 0,   sim: 1,  date: '2026-10-13T17:53:00' },
      { id: 's7', file: 'Exposing stealth.docx',                    status: 'failed', date: '2026-10-06T14:51:00' },
    ],
  },

  // Editor (Workspace). The sample document doubles as the "Welcome tour".
  editor: {
    sampleTitle: 'Welcome tour — sample document',
    detectPrice: '[N] credits',
    humanizePrice: '[N] credits',
    citePrice: '[N] credits',
    citeStyles: ['APA 7', 'Harvard', 'MLA', 'Chicago'],
    blockStyles: [{ tag: 'p', label: 'Normal text' }, { tag: 'h1', label: 'Heading 1' }, { tag: 'h2', label: 'Heading 2' }, { tag: 'h3', label: 'Heading 3' }],
    sampleHtml: `<h1>The Impact of Renewable Energy on Modern Power Grids</h1>
<p>Renewable energy sources are changing how electricity is generated and delivered across modern power systems.</p>
<h2>Introduction</h2>
<p>Over the past decade, solar and wind capacity has grown quickly around the world. It is important to note that governments and utilities are investing heavily in grid modernization to accommodate variable generation. This shift requires new planning tools, storage and regulation. In today's rapidly evolving energy landscape, understanding these dynamics is crucial for policymakers and engineers alike.</p>
<h2>Challenges</h2>
<p>Wind and solar output depends on the weather, so grid operators must balance supply and demand in real time. Furthermore, aging transmission lines were not designed for two-way power flows. Battery storage helps, but it remains expensive at scale.</p>
<h2>Conclusion</h2>
<p>In conclusion, renewable energy plays a pivotal role in shaping the future of power grids. Moreover, continued investment in flexible infrastructure will be essential to ensure a reliable and sustainable energy system.</p>`,
  },

  // Slides. Design colors belong to the slide themes (the student's deck), not to the app UI.
  slides: {
    price: '30 credits',
    topicPlaceholder: 'Turn your idea into polished slides in minutes — describe the topic…',
    // Tone and language are picked by the model from the request
    defaults: { count: 8, photos: true },
    counts: [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    fileAccept: '.pdf,.docx,.pptx,.txt,.md,.jpg,.jpeg,.png',
    fileTypes: 'PDF, DOCX, PPTX, TXT or a photo',
    perSlidePrice: 3,           // price = base + per slide (title included); web research and photos are included
    researchMaxChars: 1500,     // longer requests count as pasted material, not a bare topic
    trustNote: 'Credits are refunded automatically if generation fails. You can switch styles after generating — free.',
    designCategories: ['Academic', 'Work', 'Finance', 'Promotion', 'Consulting'],
    designs: [
      { id: 'blue',   name: 'DocMaxxing Blue',         category: 'Academic',   bg: '#0f1b3d', fg: '#ffffff', accent: '#60a5fa' , sample: 'Renewable Energy in Central Asia' },
      { id: 'paper',  name: 'Paper White Courseware',  category: 'Academic',   bg: '#f7f5ef', fg: '#1f2328', accent: '#2563eb' , sample: 'Forest Ecosystems and Carbon Storage' },
      { id: 'teal',   name: 'Teal Academic Defense',   category: 'Academic',   bg: '#0f3b3a', fg: '#f0fdfa', accent: '#5eead4' , sample: 'Coastal Bird Migration Patterns' },
      { id: 'atlas',  name: 'Deep Blue Atlas',         category: 'Work',       bg: '#0b1d33', fg: '#e6eef8', accent: '#f59e0b' , sample: 'Mountain Tourism Development Plan' },
      { id: 'clay',   name: 'Warm Clay Works',         category: 'Work',       bg: '#f3e6dc', fg: '#3b2418', accent: '#c2410c' , sample: 'Opening a Neighborhood Coffee Shop' },
      { id: 'gold',   name: 'Black Gold Ledger',       category: 'Finance',    bg: '#111111', fg: '#f5f5f5', accent: '#d4af37' , sample: 'Quarterly Investment Review' },
      { id: 'jade',   name: 'Warm Jade Annual Report', category: 'Finance',    bg: '#eef6f1', fg: '#12352a', accent: '#0f766e' , sample: 'Sustainable Forestry Fund Report' },
      { id: 'night',  name: 'Electric Night',          category: 'Promotion',  bg: '#120b2e', fg: '#ffffff', accent: '#f472b6' , sample: 'Urban Soundscape Trends 2026' },
      { id: 'silk',   name: 'Silk Yellow Magazine',    category: 'Promotion',  bg: '#fff7d6', fg: '#1c1917', accent: '#a16207' , sample: 'Slow Mornings: A Café Lifestyle Guide' },
      { id: 'pine',   name: 'Pine Green Strategy',     category: 'Consulting', bg: '#f4f7f2', fg: '#14301f', accent: '#166534' , sample: 'Five-Year Land Use Strategy' },
      { id: 'indigo', name: 'Indigo Due Diligence',    category: 'Consulting', bg: '#1e1b4b', fg: '#eef2ff', accent: '#a5b4fc' , sample: 'Laboratory Network Expansion Review' },
    ],
  },

  // Formatting. All labels and option values here are shown as-is in the UI.
  format: {
    guestNeedsSignup: true,              // guests see "Create your free account" when they press Format
    defaultStyle: 'harvard',             // used unless the user picked another style
    maxFileMb: '[N]',
    // Style defaults are MOCK values: replace them with the real formatting profiles.
    // profileHeadingPt / profileMarginIn are what "— profile default —" and "From profile" resolve to (mock).
    styles: [
      { id: 'harvard', label: 'Harvard (Cite Them Right)', short: 'Harvard', hint: 'Author–date. Common in the UK and Australia.', profileHeadingPt: 14, profileMarginIn: 1,
        defaults: { coverPage: true, coverTitle: '', coverStudent: '', coverLecturer: '', coverCourse: '', coverDate: '',
          toc: true, tocDepth: 2, tocWordField: true, abbrev: false, abbrevList: '', appendices: false, appendixLetters: true,
          autoCaptions: true, tableCaption: 'Above table', figureCaption: 'Below figure', requiredSections: '',
          references: true, refHeading: 'Reference list', refNewPage: true, refNumbered: false, citationStyle: 'same',
          font: 'Times New Roman', size: 12, lineSpacing: '1.5', alignment: 'Left', firstLineIndent: false,
          headingSize: 'profile', margins: 'normal', pageSize: 'A4', pageNumbers: 'Bottom center' } },
      { id: 'apa', label: 'APA 7', short: 'APA 7', hint: 'Psychology, education and social sciences.', profileHeadingPt: 12, profileMarginIn: 1,
        defaults: { coverPage: true, coverTitle: '', coverStudent: '', coverLecturer: '', coverCourse: '', coverDate: '',
          toc: false, tocDepth: 2, tocWordField: true, abbrev: false, abbrevList: '', appendices: false, appendixLetters: true,
          autoCaptions: true, tableCaption: 'Above table', figureCaption: 'Above figure', requiredSections: '',
          references: true, refHeading: 'References', refNewPage: true, refNumbered: false, citationStyle: 'same',
          font: 'Times New Roman', size: 12, lineSpacing: '2.0', alignment: 'Left', firstLineIndent: true,
          headingSize: 'profile', margins: 'normal', pageSize: 'Letter', pageNumbers: 'Top right' } },
      { id: 'mla', label: 'MLA 9', short: 'MLA 9', hint: 'Humanities and literature.', profileHeadingPt: 12, profileMarginIn: 1,
        defaults: { coverPage: false, coverTitle: '', coverStudent: '', coverLecturer: '', coverCourse: '', coverDate: '',
          toc: false, tocDepth: 1, tocWordField: true, abbrev: false, abbrevList: '', appendices: false, appendixLetters: true,
          autoCaptions: true, tableCaption: 'Above table', figureCaption: 'Below figure', requiredSections: '',
          references: true, refHeading: 'Works Cited', refNewPage: true, refNumbered: false, citationStyle: 'same',
          font: 'Times New Roman', size: 12, lineSpacing: '2.0', alignment: 'Left', firstLineIndent: true,
          headingSize: 'profile', margins: 'normal', pageSize: 'Letter', pageNumbers: 'Top right' } },
      { id: 'chicago', label: 'Chicago 17', short: 'Chicago 17', hint: 'History and some business courses.', profileHeadingPt: 12, profileMarginIn: 1,
        defaults: { coverPage: true, coverTitle: '', coverStudent: '', coverLecturer: '', coverCourse: '', coverDate: '',
          toc: false, tocDepth: 2, tocWordField: true, abbrev: false, abbrevList: '', appendices: false, appendixLetters: true,
          autoCaptions: true, tableCaption: 'Above table', figureCaption: 'Below figure', requiredSections: '',
          references: true, refHeading: 'Bibliography', refNewPage: true, refNumbered: false, citationStyle: 'same',
          font: 'Times New Roman', size: 12, lineSpacing: '2.0', alignment: 'Left', firstLineIndent: true,
          headingSize: 'profile', margins: 'normal', pageSize: 'Letter', pageNumbers: 'Bottom center' } },
      { id: 'ieee', label: 'IEEE', short: 'IEEE', hint: 'Engineering and computer science. Numbered references.', profileHeadingPt: 10, profileMarginIn: 0.75,
        defaults: { coverPage: false, coverTitle: '', coverStudent: '', coverLecturer: '', coverCourse: '', coverDate: '',
          toc: false, tocDepth: 2, tocWordField: true, abbrev: false, abbrevList: '', appendices: false, appendixLetters: true,
          autoCaptions: true, tableCaption: 'Above table', figureCaption: 'Below figure', requiredSections: '',
          references: true, refHeading: 'References', refNewPage: false, refNumbered: true, citationStyle: 'same',
          font: 'Times New Roman', size: 10, lineSpacing: '1.0', alignment: 'Justified', firstLineIndent: false,
          headingSize: 'profile', margins: 'narrow', pageSize: 'Letter', pageNumbers: 'Top right' } },
    ],
    options: {
      font: ['Times New Roman', 'Arial', 'Calibri', 'Cambria', 'Georgia', 'Verdana', 'Tahoma'],
      size: [10, 11, 12, 13, 14, 16, 18],
      lineSpacing: ['1.0', '1.15', '1.5', '2.0'],
      alignment: ['Left', 'Justified', 'Center', 'Right'],
      headingSize: [{ value: 'profile', label: '— profile default —' }, 14, 16, 18, 20],
      margins: [{ value: 'normal', label: 'Normal (1")' }, { value: 'narrow', label: 'Narrow (0.5")' }, { value: 'wide', label: 'Wide (1.5")' }, { value: 'profile', label: 'From profile' }],
      pageSize: ['A4', 'Letter'],
      pageNumbers: ['None', 'Top left', 'Top center', 'Top right', 'Bottom left', 'Bottom center', 'Bottom right'],
      tocDepth: [1, 2, 3, 4],
      tableCaption: ['Above table', 'Below table'],
      figureCaption: ['Above figure', 'Below figure'],
      citationStyle: 'styles',            // "Same as document style" + every style label
    },
    numericFields: ['size', 'tocDepth', 'headingSize'],
    // Text the student typed is kept when they switch styles
    keepOnStyleChange: ['coverTitle', 'coverStudent', 'coverLecturer', 'coverCourse', 'coverDate', 'abbrevList', 'requiredSections'],
    // Settings panel. Each section's toggle hides its fields when off (unless alwaysShow).
    schema: {
      structure: [
        { title: 'Cover page', toggle: 'coverPage', fields: [
          { key: 'coverTitle', label: 'Title', type: 'text' }, { key: 'coverStudent', label: 'Student', type: 'text' },
          { key: 'coverLecturer', label: 'Lecturer', type: 'text' }, { key: 'coverCourse', label: 'Course', type: 'text' },
          { key: 'coverDate', label: 'Submission date', type: 'date' }] },
        { title: 'Table of contents', toggle: 'toc', fields: [
          { key: 'tocDepth', label: 'Depth', type: 'radio', options: 'tocDepth' }, { key: 'tocWordField', label: 'Word TOC field', type: 'switch' }] },
        { title: 'List of abbreviations', toggle: 'abbrev', fields: [
          { key: 'abbrevList', label: 'Abbreviations', type: 'textarea', placeholder: 'AI — artificial intelligence', hint: 'Format: "CODE — meaning", one per line.' }] },
        { title: 'Appendices', toggle: 'appendices', fields: [{ key: 'appendixLetters', label: 'Letter labels (A, B, C…)', type: 'switch' }] },
        { title: 'Captions', toggle: 'autoCaptions', toggleLabel: 'Auto-number captions', alwaysShow: true, fields: [
          { key: 'tableCaption', label: 'Table caption', type: 'radio', options: 'tableCaption' },
          { key: 'figureCaption', label: 'Figure caption', type: 'radio', options: 'figureCaption' }] },
        { title: 'Required sections', fields: [
          { key: 'requiredSections', label: 'Required sections', type: 'textarea', placeholder: 'Introduction\nMethodology',
            hint: 'One section title per line. Parsed from the brief when available.' }] },
        { title: 'References', toggle: 'references', toggleLabel: 'Include a reference list', fields: [
          { key: 'refHeading', label: 'Section heading', type: 'text' }, { key: 'refNewPage', label: 'Start on a new page', type: 'switch' },
          { key: 'refNumbered', label: 'Numbered list (IEEE)', type: 'switch' },
          { key: 'citationStyle', label: 'Citation style', type: 'select', options: 'citationStyle' }] },
      ],
      appearance: [
        { title: 'Appearance', fields: [
          { key: 'font', label: 'Font', type: 'select', options: 'font' }, { key: 'size', label: 'Size (pt)', type: 'select', options: 'size' },
          { key: 'lineSpacing', label: 'Line spacing', type: 'radio', options: 'lineSpacing' },
          { key: 'alignment', label: 'Alignment', type: 'radio', options: 'alignment' },
          { key: 'firstLineIndent', label: 'First-line indent (0.5")', type: 'switch' },
          { key: 'headingSize', label: 'Heading size (pt)', type: 'select', options: 'headingSize' },
          { key: 'margins', label: 'Margins', type: 'select', options: 'margins' },
          { key: 'pageSize', label: 'Page size', type: 'radio', options: 'pageSize' },
          { key: 'pageNumbers', label: 'Page numbers', type: 'select', options: 'pageNumbers' }] },
      ],
    },
    fontStacks: {
      'Times New Roman': '"Times New Roman", Times, serif', Arial: 'Arial, Helvetica, sans-serif', Calibri: 'Calibri, Carlito, sans-serif',
      Cambria: 'Cambria, Caladea, Georgia, serif', Georgia: 'Georgia, serif', Verdana: 'Verdana, sans-serif', Tahoma: 'Tahoma, Verdana, sans-serif',
    },
    sampleParagraphs: [
      'This report looks at how small changes in daily routines affect study habits. It draws on a short survey of first-year students and on recent published research.',
      'The results suggest that regular breaks and a fixed place to study help students stay focused for longer. The next section explains how the data was collected.',
      'Participants answered ten questions about their weekly schedule. Responses were grouped by year of study and compared across three periods.',
    ],
    sampleRefs: {
      harvard: ['Brown, L. (2020) Study skills for university. 3rd edn. London: Sage.', 'Smith, J. and Lee, K. (2022) ‘Routines and focus’, Journal of Learning, 14(2), pp. 45–60.'],
      apa: ['Brown, L. (2020). Study skills for university (3rd ed.). Sage.', 'Smith, J., & Lee, K. (2022). Routines and focus. Journal of Learning, 14(2), 45–60.'],
      mla: ['Brown, Laura. Study Skills for University. 3rd ed., Sage, 2020.', 'Smith, John, and Kim Lee. “Routines and Focus.” Journal of Learning, vol. 14, no. 2, 2022, pp. 45–60.'],
      chicago: ['Brown, Laura. 2020. Study Skills for University. 3rd ed. London: Sage.', 'Smith, John, and Kim Lee. 2022. “Routines and Focus.” Journal of Learning 14 (2): 45–60.'],
      ieee: ['L. Brown, Study Skills for University, 3rd ed. London, U.K.: Sage, 2020.', 'J. Smith and K. Lee, “Routines and focus,” J. Learn., vol. 14, no. 2, pp. 45–60, 2022.'],
    },
  },

  // Work Review
  review: {
    disclaimer: "AI review. This is an opinion based on the checks, not your instructor's grade.",
    docTypes: ['Essay', 'Report', 'Literature Review', 'Research Paper', 'Case Study', 'Reflection', 'Learning Journal', 'Dissertation Chapter', 'Thesis chapter', 'Other'],
    verdicts: [{ min: 85, text: 'Ready to submit' }, { min: 70, text: 'Ready after small fixes' }, { min: 55, text: 'Almost ready' }, { min: 0, text: 'Needs more work' }],
    statuses: {
      met: { label: 'Met', icon: 'check' }, partly: { label: 'Partly', icon: 'half' },
      missing: { label: 'Missing', icon: 'close' }, notChecked: { label: 'Not checked', icon: 'minus' },
    },
  },

  // Landing page (draft structure). Sections top to bottom; numbers are real (Oct 2026).
  landing: {
    nav: [['tools', 'Tools'], ['how', 'How it works'], ['pricing-land', 'Pricing'], ['veil-land', 'Veil'], ['faq', 'FAQ']],
    title: 'Pass the AI check. Sound like you.',
    subtitle: 'AI and plagiarism check before you submit, humanizing for flagged parts and free reference formatting. All in one place.',
    cta: 'Start free with 50 credits',
    secondaryCta: 'Try without an account',
    stats: [['500+', 'documents checked', 'fileCheck'], ['300', 'students', 'users'], ['50', 'free credits to start', 'gift']],
    howTitle: 'How it works',
    steps: [
      { icon: 'scan', shot: 'check', title: 'Check', text: 'Upload your essay. Get AI and plagiarism scores and see which parts look AI-written.' },
      { icon: 'sparkles', shot: 'humanize', title: 'Humanize', text: 'Rewrite only the flagged parts so they read naturally, then check again in one click.' },
      { icon: 'align', shot: 'format', title: 'Format & submit', text: 'Apply APA, MLA, Harvard or Chicago to the whole document. Free, always.' },
    ],
    toolsTitle: 'Every tool for your paper',
    toolsSub: 'Open any tool. You see the cost before anything runs.',
    videoTitle: 'See it in 2 minutes',
    videoText: 'A quick walkthrough of checking, humanizing and formatting a real essay.',
    veilTitle: 'Veil: DocMaxxing in your browser',
    veilText: 'Check and humanize text right where you write: Google Docs, Canvas, Moodle. No copy-paste.',
    pricingTitle: 'Simple pricing',
    pricingSub: 'Pick a plan or buy credits once. Credits come back if a run fails.',
    reviewsTitle: 'What students say',
    reviewsSub: 'Real messages from our Telegram channel.',
    // Real Telegram chats, retyped as bubbles: names, avatars and file names that carry names are left out
    reviews: [
      { tag: 'Case study', quote: 'Thanks a lot, bro, for the work and for your patience!', msgs: [
        { me: true, file: 'Case_part_2.docx', size: '20.6 KB', time: '20:54' },
        { me: true, text: 'работа готова 2 части кейса', time: '20:54' },
        { text: 'спасибо большое брат, за работу и за терпение!', time: '23:18' },
        { me: true, text: 'Обращайтесь брат 🤝', time: '13:04', react: '🤝' } ] },
      { tag: 'Midterm report', quote: 'Thank you so much!', msgs: [
        { me: true, file: 'Midterm_Workbook.xlsx', size: '29.9 KB', time: '19:36' },
        { me: true, file: 'Midterm_Report.docx', size: '360.1 KB', time: '19:52' },
        { text: 'Спасибо большое вам', time: '23:11' },
        { me: true, text: 'всегда пожалуйста!', time: '23:11' } ] },
      { tag: 'Economics task', quote: 'Thank you very much', msgs: [
        { me: true, text: 'Three people are also below 2.5 (1, 1, 2), so the poverty rate is 3/5 = 60%. Thus on a headcount measure, the countries are equal in terms of poverty.', time: '12:06' },
        { text: 'спасибо большое', time: '12:52', react: '🤝' } ] },
      { tag: 'Assignment', quote: 'All spot on, bro. Thanks', msgs: [
        { text: 'Все четко брат', time: '19:41' },
        { text: 'Спасибо', time: '19:41' },
        { me: true, text: 'всегда пожалуйста 🙏', time: '20:08', react: '❤️' } ] },
    ],
    reviewsUrl: 'https://t.me/docmaxxing',
    faqTitle: 'Questions',
    faq: [
      ['Are my documents private?', 'Your files are used only to run the tool you picked. We don’t publish them or share them with your university.'],
      ['How is your AI check different from my university’s?', 'We run the same kind of AI and similarity check, so you see the result before you submit, not after.'],
      ['What if a check fails?', 'Credits for a failed run come back to your balance automatically.'],
      ['How do credits work?', 'Each paid run costs credits, shown before you start. Formatting and Work Review are free. You get 50 credits when you sign up.'],
      ['Can I get a refund?', 'Yes, see our Refund Policy. Write to support and we’ll sort it out.'],
    ],
    finalTitle: 'Ready to check your essay?',
    finalText: '50 free credits. No card needed.',
  },

  signup: {
    perks: ['50 free credits to start', 'Formatting and Work Review are free', 'Cost shown before every run'],
  },

  // Guided tours, one per tool. Shown once on the first visit, then via "Take the tour".
  // route = page it runs on; target = CSS selector of the block to highlight.
  // Optional textSample (sample text was loaded for the tour) and textGuest (signed out).
  tours: {
    scan: { route: 'turnitin', steps: [
      { target: '#scan-drop', title: 'Upload your document',
        text: 'Drop a .docx or .pdf here, or browse. We check the whole document, the way your university does.',
        textSample: 'Drop a .docx or .pdf here, or browse. We attached a sample document so you can try it right away.' },
      { target: '#scan-run-area', title: 'See the cost first',
        text: 'The cost is shown before you check. Credits are spent only when you press Check document, and refunded if a check fails.',
        textGuest: 'Sign up to check documents. You get 50 credits to start.' },
      { target: '#scan-latest', title: 'Read the result',
        text: 'A clear verdict, AI and similarity scores with Low / High levels, both reports to download, and one click to see the AI parts or humanize the text.' },
      { target: '#scan-history', title: 'Previous checks',
        text: 'Every check stays here with both reports. Checks in progress and failed checks are marked right in the row.' },
    ] },
    // Only the steps whose blocks are on screen run: the first set on the upload screen,
    // the last set once the brief is parsed (chat). Never more than 4 at a time.
    assignment: { route: 'assignment', steps: [
      { target: '#assign-page .tool-head', title: 'How it works',
        text: 'Three steps: attach your brief, check the price, then review and download. You pay only after you confirm the price.' },
      { target: '#assign-composer', title: 'Attach your brief and describe the task',
        text: 'Press + or drop files anywhere on the page: the brief, rubric or readings. Add details like topic, length or deadline, then press send to get a price. Later, use the same box to ask for changes.' },
      { target: '.examples', title: 'Not sure what to write?',
        text: 'Pick an example to see what kind of tasks we help with: essays, case studies, literature reviews and reports.' },
      { target: '.brief-grid', title: 'Check what we understood',
        text: 'We read your brief and filled in the requirements. Fix any field that is wrong before you confirm.' },
      { target: '.price-box', title: 'Confirm the price',
        text: 'This is the full price, and your balance is shown next to it. Nothing is charged until you press Confirm and continue.' },
    ] },
    // Setup screen shows the first four; after generating, the last three.
    slides: { route: 'presentation', steps: [
      { target: '#sl-topic-block', title: 'Describe your topic',
        text: 'Type what the presentation is about. The card on the left is your design. Press + to turn a document into slides instead.' },
      { target: '#sl-settings-block', title: 'Settings are ready',
        text: 'Number of slides and photos are already set. Tone and language follow your request.' },
      { target: '#sl-generate', title: 'See the price, then generate',
        text: 'Generating costs 30 credits, shown before you start. If generation fails, credits come back automatically.' },
      { target: '#sl-viewer', title: 'Click any text to edit',
        text: 'Change titles and points right on the slide. Edits are free and save automatically.' },
      { target: '#sl-designs', title: 'Pick a design',
        text: 'Choose how your slides look. You can switch designs after generating, for free.' },
      { target: '#sl-download', title: 'Download',
        text: 'Get your slides as a .pptx file. It opens in PowerPoint, Google Slides and Keynote.' },
    ] },
    // Preview tip lives in step 3 (on narrow screens the preview is a drawer, so it can't be highlighted)
    review: { route: 'check', steps: [
      { target: '#rv-doc', title: 'Add your work',
        text: 'Paste your text or upload a .docx or .pdf. It stays here for Formatting too, so you add it once.' },
      { target: '#rv-brief', title: 'Add the brief for a full check',
        text: 'Paste or upload the task from your lecturer. We find its requirements, like word count and style. Without a brief you get a basic check.' },
      { target: '#rv-run', title: 'Check for free',
        text: 'Pick the type of work and press Check document. Work Review is free.' },
      { target: '#rv-results', title: 'Score and action plan',
        text: 'You get a readiness score, each requirement marked Met, Partly or Missing, and a plan with a button to the right tool for each fix.' },
    ] },
    format: { route: 'format', steps: [
      { target: '#fmt-step-1', title: '1. Add your document',
        text: 'Upload a .docx or switch to Paste text. Until you add a document, the preview shows sample text.' },
      { target: '#fmt-step-2', title: '2. Pick a style',
        text: 'The style sets fonts, spacing and structure in one click. Have a brief from your lecturer? Choose Auto-fill from brief and we fill in the settings.' },
      { target: '#fmt-step-3', title: '3. Settings, only if needed',
        text: 'Everything already comes from the style. Press Edit settings to change details: changed fields are marked, and the preview shows every change live.' },
      { target: '#fmt-bar', title: 'Format for free',
        text: 'Formatting is free. Press Format document and download the result as .docx.',
        textGuest: 'Formatting is free. Create a free account to format and download your document.' },
    ] },
    editor: { route: 'workspace', steps: [
      { target: '#doc p', title: 'Select any text',
        text: 'Select a sentence or a paragraph. A Humanize button appears right next to it.' },
      { target: '#ed-check', title: 'Find AI-looking parts',
        text: 'Check the whole document. Parts that look AI-written get a red underline, and the arrows jump between them.' },
      { target: '#ed-fix', title: 'Humanize and review',
        text: 'Humanize a selection or all AI parts at once. Changes appear like track changes in Word: accept or reject each one.' },
      { target: '#ed-export', title: 'Download when ready',
        text: 'Everything saves automatically. Export to .docx, or print or save as PDF, when you are done.' },
    ] },
    humanizer: { route: 'humanizer', steps: [
      { target: '#hum-input', title: 'Add your text',
        text: 'Paste your text, or switch to File to upload a .docx, .pdf or .txt.',
        textSample: 'Paste your text, or switch to File to upload a .docx, .pdf or .txt. We loaded a sample text so you can try it right away.' },
      { target: '#hum-meta', title: 'See the cost first',
        text: 'The word count and the cost update as you type, so you know the price before you run. Up to 5 000 words at a time.',
        textGuest: 'Without an account you get 1 free run. Sign up to get 50 credits for more.' },
      { target: '#run-btn', title: 'Humanize',
        text: 'Press Humanize to rewrite the text. The result appears below with Copy and Check for AI, which sends it straight to AI Detector.' },
      { target: '.hdr-credits', targetGuest: '.sidebar-foot', title: 'Your credits',
        text: 'Your balance is always here, next to See Pricing. Every charge is listed in Credit history on Home.',
        textGuest: 'Sign up to get 50 credits. Formatting and Work Review are free.' },
    ] },
  },

  assignment: {
    title: 'Upload your assignment brief',
    subtitle: 'We read the requirements and show you a price before you pay',
    steps: ['Attach your brief', 'Check the price', 'Review and download'],
    formats: 'PDF, DOC, DOCX, TXT or images',
    maxFileSizeMb: 16,                       // Flask MAX_CONTENT_LENGTH, all files together
    instructionsLabel: 'Add instructions',
    instructionsPlaceholder: 'Topic, length, citation style, deadline',
    composerPlaceholder: 'Attach your brief or describe the task: topic, length, citation style, deadline',
    examples: [
      { label: 'Essay, 1500 words, Harvard', text: 'Argumentative essay, 1500 words, Harvard referencing. Topic: should universities ban AI tools? Deadline: next Friday.' },
      { label: 'Case study analysis',        text: 'Case study analysis of a company entering a new market, 2000 words, APA 7. Use at least 5 academic sources.' },
      { label: 'Literature review',          text: 'Literature review on remote learning and student wellbeing, 2500 words, APA 7, sources from the last 10 years.' },
      { label: 'Report with sources',        text: 'Business report with an executive summary and recommendations, 1800 words, Harvard, at least 8 sources.' },
    ],
    briefFields: [
      { key: 'type',         label: 'Type of work' },
      { key: 'length',       label: 'Length' },
      { key: 'style',        label: 'Citation style', options: ['Harvard', 'APA 7', 'MLA 9', 'Chicago', 'Not specified'] },
      { key: 'deadline',     label: 'Deadline' },
      { key: 'language',     label: 'Language', readonly: true },
      { key: 'requirements', label: 'Key requirements', multiline: true },
    ],
    refinements: ['Shorten', 'Add sources', 'Make it more formal', 'Explain the structure'],
  },

  support: { label: 'Help & support', description: 'Questions about your account, credits or payments' },

  mockDocuments: [
    { id: 'd1', title: 'Climate policy essay — final',      tool: 'humanizer',  date: '2026-10-19' },
    { id: 'd2', title: 'Marketing report draft',            tool: 'turnitin',   date: '2026-10-18', ai: 34 },
    { id: 'd3', title: 'Psychology lit review (Harvard)',   tool: 'format',     date: '2026-10-16' },
    { id: 'd4', title: 'Business ethics case study',        tool: 'assignment', date: '2026-10-14' },
    { id: 'd5', title: 'Group project pitch',               tool: 'presentation', date: '2026-10-11' },
    { id: 'd6', title: 'History coursework — self check',   tool: 'check',      date: '2026-10-09' },
    { id: 'd7', title: 'Marketing report (APA 7)',          tool: 'format',     date: '2026-10-08' },
    { id: 'd8', title: 'Case study draft — review',         tool: 'check',      date: '2026-10-07' },
  ],
};

/* =========================================================
   Icons — one inline SVG set (24×24, stroke)
   ========================================================= */
// Brand mark (app icon from the designer), 128×128 PNG shown at 32×32
const LOGO_SVG = `<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAAAeGVYSWZNTQAqAAAACAAEARoABQAAAAEAAAA+ARsABQAAAAEAAABGASgAAwAAAAEAAgAAh2kABAAAAAEAAABOAAAAAAAABaAAAAABAAAFoAAAAAEAA6ABAAMAAAABAAEAAKACAAQAAAABAAAAgKADAAQAAAABAAAAgAAAAACPIgiLAAAACXBIWXMAAN11AADddQGsh8ODAAABWWlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iWE1QIENvcmUgNi4wLjAiPgogICA8cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiPgogICAgICA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0iIgogICAgICAgICAgICB4bWxuczp4bXA9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC8iPgogICAgICAgICA8eG1wOkNyZWF0b3JUb29sPkZpZ21hPC94bXA6Q3JlYXRvclRvb2w+CiAgICAgIDwvcmRmOkRlc2NyaXB0aW9uPgogICA8L3JkZjpSREY+CjwveDp4bXBtZXRhPgoE/1zIAAAbN0lEQVR4Ae1de4xdxX2emXP3ae/T9q4XP1k/UpIQcHg2gUAbFyWhalq1BKRWFFUp+av9o0qD0v5jqaoiaFWpVJWKU1ogfaWoJbRN0hIqQCQEUCWTkogUbMDYCGxgvbu293nPmX7fb86ce+7u3fXeffiec/eMfXfmzpmZM/P7vt9v5szjXK3Wyh2y5vJTqmcyVP3GzvZHKuq3KupT1nQbY7erSO20Wm3VSiFO9URadRurWpW2OlK6VyttFC40jbNojLajbB6C09ros2jbOFr4Aa6c1lqdwIXjyphxtHssKEcjoTIjna1tH7w8qMbUIYhlDRzkvzpu9122t1SauhK4Xad0dEBZvQ8lE+AeNHiDNi1K6QCf+H4WTbdoE3z+c2DHgPNaMzqg7Bx9UJzCYJzEg++MFlGEEM0sk04gchT+OyDPUSjPEaXM8+XZcz9686E+xq/Y8ZYrcFbvuXvqZqOC3wCIB1HZnSZokTaoKAK2IcpGiwTQJgV1BdJbPKsnBmhCxTFG+BGFJEb0llbmySgK//7Y9nufVocOLds6LJsAe7409RkA/2Vro0/roBV1KoO1MeCLt6y4uiIJsHMkIUrKhjMoST9jdHTfqw+0f2c5xdZNgOHfHt9vTPsfQbG/QLNuw2nct9Du5Qh/5XlAhqAt7i7sozac+oNjD/Ycrafcugiw/4uTd0ZB6U+0KQ3YcgF8PYJe27QgQglECMunrCrfc+xwx8NLvd+SCLD3d15r09M77sNdfpfabmHuC5c9CUAxUSmtIlu+X7e1feXoX2hq6aLuggTYfdeZ3lJr59+aoPWXo0LrFxVmNi5ieAhrAKweL89O3nWhp4VFCeDA7/imCdpuicpT2WhfUYslScC0tJMET5RnJm9fjAR4+Kztdt/1Rnuppe3hAvza8sl6bDQ7pYhdqaXjIWK5UH0XJEBQGrzXlDp+qdD8hUSX/Xhih+7g88RyodrW7AL2fPHcnSZof9gN9opHvIWEl494zhtgziCavfPo1zu+MbfO8wiw/7emhqOSeh6zT1uK0f5cceXzuxDAhu9jYvZnjz3YXjVPMKcLwEpFEN2HyYUC/HxiXbPWVGRgulmb6Gt4jK9S+qovbnq39G1kADEK019TmrmNlK4gsrb82aOH25/wzUgswM0325KJoj9Eh1GA76XTVD4UmthG9qu33WaxmOBcQoCTe8s3KNPyCbfA4C8XfjNJQLA1wU1HeqZu9O1KCKBU+U4MFgrt95JpSt9ibqAFU4XqTt88IcDw3SM9iDwYFXP8Xi5N6wvG1v7C8N22h40UAhjbcaVSAbZpFYs8TYu8bxgx1i3bjMXuLU8AjPivF9PgExV+U0vABCWttb2OjXRjAKsOFA99TY15VeMEa6sPOALwkUCrfdzDV7h1IgHu11R6vwL25vLNY92YIhhyGzjXiQDWeTOJNbb1DBF7MzHTvglswIiw6ATWDy+AOLbrE3vsL4360fAOt3V7/YhgXbdUtunrjsCYPhOWTD8mgECIwgKsH1LAAgBzntbCU0DUIyd21k/ri5ZSAjhsYo3uxeKA7pYjJ4VY1pcEuA4c2h6c01S7Cuu/vrCX1rLH1+EOg+0BO4r+fx0SAFpvrNlRgvkfwIaxppbA3MPGtYa7tIjJ4d2mlkbcOGDO4/kc/m9qRgsQgtMEuh2n0tt4Mh3/sB0GIGM1FEPfQLswJkSE/7M41zqFs5YzXCuBUAI3Sd7EVJCW9/MsUbedqyI5bjZesiBj2l0DWl06GKnuDqtKGOiwidJMgEuAdTzwYRy+4n0VWpVDrUYntDr+nlYn33fxzWoViLnRursEtehCZ5BjyCtVp9b3btDquv2R6movq/NTkZqYjIGvJFswZMCErjalrttr1PBAST33fxgoo0wSpPkcNQJvZUHDcGok/wQgUAM9Wh28IlSBmlUjZyM1G29vEI2n1l/gQykwD/P2ds6qa/Y6AjQf+GwRCWBb+RSQe4LTjG8EjW/4cKjOni+rabxEg9q8XMe8ZyetGuotq629zUwCTAhCL3rzvg4QggBX441EsxjBlTGYW41+mySYmI7U5TtpF5rQQWus5kxgzrs4Dvq2dCu1uStU53EafjXA93CzO+jfGKqdW7BlFl1MEzo+EOXbse/fBYBmZsJVBZ9EKmH3/NSMFSuwki4lyxLOPQFaANKWPivP8Cvo9qswYjkEHI9JeEjCiwxhBYbxwjt2L83mck0A7mIbwIJmP7qAMgcCq+RkogiS8f40rMCVl0ZiEVbpFpkpJtcEoPnft80oWoHVcgTdfbTMBnJGkPtnejsi9aFtWnHGsJlcbglAfW/HpA37fzfwW3kHQLMfxKZ/LhGmZ636+LCVqWU+djaLyy0B+E7Koc0GM36RasOJNgK2EkcSVWm+kAFWQAjhrEAXrMDlu5vLCqxQbCsR+cryUgn3XgJ0MEprxXG3jnaz7OkMgk9TH8AEpDXfhwOwgNdnYAUOXGrVxg5Ooq2s/lnJnUsCUPgbAMJ2rGPKXD0i+nqwxWmZoMiIPwafGi8fSMYTQLoGSgrXNsLiXDXcPFYglwQg6DsGjNrY6hAP8QTQtxGDQViCejlAzSbQ3tQ70GEJalgFWghOM398D+8nxicrirzseuSSANREmv8I5p972ugI4JZ+bHIHOZbqBHiCD2DTYdcdgBjoG4QQQgbXDZAY7SDe9R9qjnmB3BGAEzO9G7Ua6oMGAmzgIdpaLls10FvCkwGswBLMgGg4MhsEvBVg2FmAVHwMPtM7ksD8Y4qYY4FB/KxFPYRbKjEvZrrcESDE6H83ZuXaStzR4x8Bna+B/I7B+PcKFpFiesSfAIvIWkSgdahlEVqxy+jGD+d/jSB3BAgw6SPmHxqPI84JCcAFxbFAT6dRm3oDGRzW4gDBd4DWBjYgEajt8klbBJ/PWQdagY/tVmrnZr3gvWrdP2txuSIAze0WmF2u/rErIOj8pF15NlLbNregn57fFTCt0/g0sCki4KLvArw18H4yHoDEfFxLYNXPfWz+fdL1yXo4VwTg6H8Ppn5LKc2ngKnV3rH754bPnUMtEp8eDvg+PNFwtN4RglpdAdaRwBGD18Uq+LS4mYvj+oNWH92FOg3ld0CYKwK04pdphrdC8DD/JkWCFP5iEfh00NWu1fYBjAdiBnjN9r5oMc29Bz4FbFrb0wPDqvGAtxaoxy0HsK0qXQnPxhz4uSEAB3+c+u3b4GbhKHDKPC13CccRHA9s6THSHRAHB3TFxFeN/gk+NVw+MSlQjgfcx89Lg/Qhfu/usu1afWRnPieHckMA9vn7IWh2/mntn88Ap3bkAc8BDGG5eNtmnn9xWkrzL8DCTwPrCZJYBGo406TSV675vI5YnH767FU6l8vFuSAAzXgnpn658kfzLzsZHc4J/mkTDMzc0wF8Hn8gCXYMBrJsLAdDYvCrRvzepIsVqAAsJInTO0LAQpAU/MR5ODbZj4mpq7GdnAdL8uRyQQAKeOcgpn7bAD6k6yvtQWecdwxL9yAB10VwGLCpy2D+oKQ2YGzA63P7dgGX4PMaEnht9yCnrUUSRloZUCITqqhuvRqLUhin+HGHr1OWfS/LLNdR6rZ/BwxtjWd/uUiw4egl4CPMxlW+a9WJFcOdgyUZG3C/nyMCyeBMeVqrBVgkSK4B5IVIwXger9w9qNUnL8uXFcg8AahN3Zj63Y4X2XBPHjXUAw18BUTxfTgmg6RjWvlURukEazMmirZtCVQ3ThFRwytEqADuB4lpIrBMbzkcGaoHj5yn+MVrjeruzI8VyDwBCPqleM5ux6SLn/kjA/BfgCP4dPyejnfAM40bzFW+MyEXdLQa7CupoU2BzB62AGlPmrmPgQI2biDdAXwhAn1IL00EdjU7MDN48MpATedkLMDDoZl2FDBH/yE25nuACGbayXfEMVqA9j6+yHdem/uJCyAROrGAFOGIFMca3Fw6i40fHD5W9/9pwGNLgDKFLPAdEZyVuvUao579cahGz7s88a0y6WXaAtCk9uO831a8xC7E418CLkTJMB0bwKB88KfK53XG4cN0SVjinMYjGs49wnVgj2Ev9hUMwCpwVZH53LgAeZHZDf5c2APufZZNMtAN4TjZrdcECkcVMu8yTQBq5F5of3rqlzKO5Sxg8498pw9xM+yATmk/49FSyStpqs29xMf55dg0tL97QyDlONArj35zieBJQWvhyTCLKeLPXR1gx1L2F4oyTYASOiiu/LmpXwewQz0GMwUqG5IAiQDDQgTEe18Igi+VdC6PXCcB4jzzQGY8bsB4sQj47scDMkhEPMvwaVjOJixY/donAxm4ogqZdZklALV/KzRoE7ZeWZp/iFCAo5/+4EsaUJrh6u9zrvu8yJdOmyYQt5adnwzxYolYq5G2ejzgAKfGJ6TAY2WaOJwQ+vQVRu3N+EJRZgnA/n/fdqMCPGB7QIFdhQgxC8TDH5eGAR92fuU7iZG2DKkw80AS8ND3GwGf284FYERWzLwjgjf1Pl58pPPWgdaAj688sn7bjdimxjFlRl1mCcBDH1z544jcE6DKh0BZ+SQO8BFACp9xc/10nCeCzytpkZfby7mSOIl3A5SAJoF1YMcaH5fL9O6asxCOCC49w97xUfBTHzHq8l0meVmFv5YVP1XdrFTJPUpt22JUb/zuEgJFJ54Pw/cAzgWUSSrXGHYAMs4/tgloqTJovkmAsbN4wwjCDlQC7cKJuYfEXF5XJsngB4AMpx2tQCvGMbfDCsy9lk7XyHAmCUDBydQv+gEKzn8EVEhLhOnBw3fKnSac8QwTIJ/WkwPRCSmYSPLgj8/DNYKz5/HqNMwHiNbLtflEYNkJ4HE4XT/eJ+24jfza/Vgo2pfNKWI0IVtO+s5OXVn5S4EloBI5uCqA0Qo2hHECPsP4yCDPh5HAk2EuYHzmn8VE0+QUJn9kMMdyKkRIVg15H8SLBUDYWwoShvdeyPHaHZ9yq5FZGw6g6tlyHP3vwq7fDfGhDwGawsUn9hzQjMJFuS5hB4KkYVoA5fO6NAAO6Qi+j2eYfX0r3pY4epb9vuvzPcje7KcBTw/0fDzLW8zxiYBnCm/8KKwALEKWXOYIQOHsw+RPxG1fqF0CGOI9cM6vAOzTeF+up9Inj3soL10GvuGcn1Zn0O/T4ccTxGoIyLw3PtIdxGGW70GXboDfLwC+FIw/fKr5AuYFNnBckyEzgKZlx1EwPV1abcOhD27pSgNZBS4upIGcH3YDNGIz7xrifFkbAP7ktJXjXqL9KYAd2NXm3lkEkqASv1Tp8b0C+/B+gYNXYKEoQ1YgUwTgyt8wV/78oY9aAAJRDyDB9WHv+26BwLjp3xRZkjilWmD2qelj59ybP5xmx/2+aL67D8tNPzn4ASDJUK/jWYJfvSFQfV1uW3u9+dci/TKasRbVcGWmD33UNP8w2cAj0WpWvlrDY9AQL4RIpU8IInlg+jHqHxkPnZlHoX5A54lA35l/RwpXnwopUEzdjuObHZjdlIWijFiBzBCAfeQmrPwNYuWPM2ce6ApwTpMdsPF11J7pHBHcdUakNZ/AeZL4vOz3z01Ymad3Zt0B6/p+ZxnSRHBkqFgHlrdcN4OxzeevC9TWvmwsFGWGANSO4UuMwrtLBTCncQ68hAQJuF7D4RNgJJDugGRgGv6jL2FPEFzE9zas/3MUdnbSmX5v0hPAcVkAR2YSwsVXfJa5Esd2bgHJf+UTeKEtuoRGu8wQoAUzZnsGof0Y/InQIWkBUPw4TLAhMRfvfcIdgyzXXVoSgeVIWvj8TrC5+WNkPBLznga3uguoAC5WAYWIpeCNVsFN47X0n7nKyB7CRr96DqJpvBOtwJk/WflDdQiWA86ZZg84K8uwv5483vn0uJi+TrwcmVwbu2D6xzHbxy7GaX4FWJbpwPbX6LtwugxX0sr+8v492OZ+GwaEbHsjXSYIQIEMD+ENH6Z625cH2hOgls8GiKYjsQCekKFCFAq4A6t83O41gdk+PvJ5UAV4/HFgMx6kQ6Hu48K8ttqOP07x81guvgy7nRv56rk1aFp9ogL28uq13QPx4A8AEhR+EsCRxn+v+E7bJQ2gR/JKep8freMVzvbxl0NG8Rp4PmnM6/dTgAsRkD+Z/mXBa+Ck3ej27rgJfxroGk4Ajv4H+vC2z40USax5EHoCPsEkkPTjeG/63XdHBIb99SQv4Ud8F9YWRvG8Tyd9PdOiTA8yQa+l+f6+knEN/nBC6Jp9uqGbRhpOAM7+DWPwx591SYMoYQgdWFWRwU/0JCAjQTqcLoPxXOXjq175oSVwYJMsKVOPsGh+TApn/l25a4B7UiQp34mTRAf2sHtKoi9qoKEEIPgcle+C+cc+zPkaHGsqSeC0uzIodFagov1pEjDM63yy4Gtk3WxfBXDfBVRpvuRBPiGBu9/FQIIy2Izfb2+UaygBOPjbinn/3g0IwDngPNixZsfxF9J8n9eDT5+zfWfQ79O8VzTfgey1PNF8SCLdDUiFLsIftuvMOdf+i3C7ebdoKAHI/kvwskeCkAbQh53WVwjhv6fJIHFoFvM4517Z0gnwJ/CjURz5e/DlMY9kQFp+km6AYcYLCXw5F8fntrEfvdG4N5E3lAAErQvPw/CqzH8F6NgKICHTMD1DrLSEGUnnfQRIqhIWenhm/1y8t89reVrDE8CRV+LFTxXlSl7Tv53Y9/j8TyP105Pu0XRNb7ZA4Y0lACpFTRQA4XtQq33Xz3vwxUetfTbfLgIvH0R0Ys2dEz4JsAQXGWsRIT0eYJkXy/EU0vH3lPqr75alLRfrvnPvw4dQPh81hAgcA9AEUl8FULxvJ9FuVIqm3lsDN+iLLYVcw5/YcR8fHay9DKgsptd42JMHSxzoFfDTgPuXQIvpRxHIXpfjXevJ49roJn6eeyVSf/ntsjo1alf19w7qagCqj1NXdtQa09+obSo8QOngY9URcv8XsAYkhfukG0rN55Qq9/b9+LhVx087k8o4ls2dub5clSYZCmN5/pp/Z0C67FphZqnXkSh8zxF/ju7lNy3q6eYlVvPHLuqqExtuo1GKph4S13WPCyVmHd4dwd5/CIYgJRVBPK/hv/hV2s/I2Dmzj2VVZCR4J9636s8ew+8GilXxqRb2k/v5QKrshXPVuML8zOvLqZEkHcXZyIYBn6oIdMHi7Ukas9J11D5VwEqDfBQ7PWbVB2fx7l+8ACItQNbIkSA1BkgBRFnzSDe7Ec4mzqIN//BU2VkCTPsW7kISEGFOGcht3BHgQhlW/zqrwOnQV044FSKg1GrnCHwFfI4F6DwH2O8TfM6g8Szff7wYJqbfpSz+Li4BSNLoswYCH6OgG+U4ACMBTo85jSewflDHOvmuQML4Q34I+NB6gk/T/5O3rPr+T/DTMYXmU0xLcjHm4xx0n6no1ZLyrmoiAjyBX/zk8zABFZMOlBNDwLshTYWiTvM5wKO1ODul1WM/QMbC1SkBzpSoD/jOxXexp6rOzKubnFr86tsWM2LuGDj7dH4IMD+saewJQQg+yRJgwuffXwgxhnCzfatbqyYvjZjD8JpIRyfS+tWoZrOPfxZm/I3TqAHCBNmTgFaBRIjwWlY+SonpB/gvHrXqyNHIPeY1quK5vS/GV1adwE9tBSdS9rVhzWFXwAHhd/4nwuSIM/j8wWYSQTQe4PM7wad7F0PX775Ylg0eLqb4W5cEIGKI9DjewKDHxL7WlXttEnNAOIqVsW/9MFTv4dGQWs85Ar6WncAzLB8MFB//YRnn+N3M4NrUpslLZZ9q7LjRkR1VNlarDLSZ44HTmB79p2dCdfIMBypa3r/LQ5W0ENwC/gy6imMYM3Cqt3DLlIBgbsYwF2NGLE9iZqEfiNtCEoyMW/WPT4Xqlbc5VnHz5xwnvHYKj3z/G2ZiJm2Zos9ANigWMA/K0UgJg8AR2NpJqFanG3JnoH6oAqdLuYP3X54tq2t/JlD7cbBydEKpp46EMhDkLGLhlikBDriAOQ7GjZQ6gqmRiXLrGMaEeMNtthxB5pPAD/DWzedfcWHWvQB/pTgBbRWNdbROf2Befr9nHIuu72gNlcugI+DsEuC5HTsMFG5FEiDWWAd6h9gb9ajGGNu+WqjVimSar8w0oVq9RuxdT6rtkUKx8oXhSmorWGMOjWUIAbC48kIU8kmgcOtBAlHI16Hr59lWIUCk219SdvZtZYoH66YngGAcnoz05EsJAV4/jNlArb9nCgI0P/4O4ydfP9yPBfjYAkirI/VIbBqaXgjrt4EyAYTz8eoRLwM3CMS3A2Ptz+LtDM/oAIfVCteUEhBso9nnth9t/75vYEKAR/FIgC1CX8McIaZeimcCL6Dm8YEpsI2M+eOnn9bJy2kSArChRw+3fc9GM/+qSzi1ULimkgAxBbaPHXug7b/SDasiADTf2sh81YbT7+tiQJiWU67DxBKYvmdC8xVinG7MHAIodezB9qNYKPg91w0UXUFaWPkME0MZ/H351b9pf31uG+YRgAmOfr3jG1E4c78puoK58srdd2JILI/99cZHalW+JgGYMCyfuicqTz9uSjhpWbhcSoDYReXJfyOWCzVgURu/+64zvaXWjm+aoO2WqDy1UBlFfAYlYFoI/vQT5ZnJ2998qG90oSouaAGYgRlZQMUSLMqXhe5RxF9UCWBxXzR/5lsXAp/VWpQATCDsaW+7PQyn7+dosng6oFSy6Tw+Npr9c9X21h2Lab5vQV0qvefuyd/UunQvbjRoyzjOk5XtxL4169bHDh95zi+fxvvGfv/VBzpqDvhqieeCFiCd6djhjodteeIGG848ytNEOuAAsS4OpYsrwiuWAIAnBsACWv/PUTR5Yz3g8/bLRm//l6Y+F1lOLNib3BxzGZXg9vKqeYYVN7EoYK4EALr8tg0nd2awiGv+G3P3f3rsgZb/nJtyKd+XTQAp/NAhs+fkPTcbE/y6VdFBDCl2mqDFUQBLClb2noMQ/oDfUmpUpIklAGi4IRI6Kvs1sY2L37Bii7/2LcQ+id9U/btjh0tPI82ytW5lBEBVvJNHxpaNV6CK1ysdHVBW78W1IVQWP6auOrXB2W1uPPV3xE/CCjFADv7Dl/hDb9ntQeYMOwGU9YuBpc84HtT010QMIU06rurz+Mp1exzgta8pa47gwgvlcvtLbz6kF3y0q0cCHo568iwt7SFrLj+leiZmpjfh13P7wxLeQ6SiHhxI68ZbYXfhdNcOtHAAFcCbAlU3fiAaPxel26y26NB0L1u/tBvlIRWmYoEcGoZTWNriTN4MZDCOFuL9KOqMnNA26i0cfj0J5eEu7TM8sBPplpGOQI28PAgSHNLQmNV3/w8VVVAKEBftwwAAAABJRU5ErkJggg==" alt="" width="32" height="32">`;

const ICONS = {
  logo: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  home: '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3"/><path d="m16 16-1.9-1.9"/>',
  sparkles: '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>',
  browser: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M10 4v4"/><path d="M2 8h20"/><path d="M6 4v4"/>',
  book: '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
  file: '<path d="m18 5-2.414-2.414A2 2 0 0 0 14.172 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2"/><path d="M21.378 12.626a1 1 0 0 0-3.004-3.004l-4.01 4.012a2 2 0 0 0-.506.854l-.837 2.87a.5.5 0 0 0 .62.62l2.87-.837a2 2 0 0 0 .854-.506z"/><path d="M8 18h1"/>',
  slides: '<path d="M2 3h20"/><path d="M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3"/><path d="m7 21 5-5 5 5"/>',
  align: '<path d="M15 12H3"/><path d="M17 18H3"/><path d="M21 6H3"/>',
  clipboard: '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
  sidebar: '<rect x="4.6" y="4.6" width="14.8" height="14.8" rx="3.4" stroke-width="1.2"/><path d="M7.6 7.6v8.8" stroke-width="1.2"/>',   /* Close.svg: collapse / expand the menu */
  panel: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/>',
  menu: '<line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/>',
  close: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
  chrome: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/><line x1="21.17" x2="12" y1="8" y2="8"/><line x1="3.95" x2="8.54" y1="6.06" y2="14"/><line x1="10.88" x2="15.46" y1="21.94" y2="14"/>',
  video: '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  flash: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
  updown: '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  coins: '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  xmark: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  laptop: '<path d="M20 16V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9m16 0H4m16 0 1.28 2.55a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45L4 16"/>',
  card: '<rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/>',
  receipt: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
  gear: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>',
  eye: '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
  fileCheck: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/>',
  gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/><path d="M7.5 8a2.5 2.5 0 0 1 0-5A4.8 8 0 0 1 12 8a4.8 8 0 0 1 4.5-5 2.5 2.5 0 0 1 0 5"/>',
  wallet: '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
  telegram: '<path d="M21 4.5 3 11.5l6 2 2 6 3.2-4.2L19 19z"/><path d="m9 13.5 8-6"/>',
  whatsapp: '<path d="M4 20l1.2-4A8 8 0 1 1 8 18.8z"/><path d="M9 9.5c0 3 2.5 5.5 5.5 5.5l1-1.5-2-1-1 .8a3.5 3.5 0 0 1-1.8-1.8l.8-1-1-2z"/>',
  instagram: '<rect width="20" height="20" x="2" y="2" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" x2="17.51" y1="6.5" y2="6.5"/>',
  youtube: '<path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"/><path d="m10 15 5-3-5-3z"/>',
  xlogo: '<path d="M5 5l14 14M19 5 5 19"/>',
  tiktok: '<path d="M14 4v10.5a3.5 3.5 0 1 1-3.5-3.5"/><path d="M14 4c.4 2.3 2 3.8 4.5 4"/>',
  phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
  redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>',
  alignLeft: '<path d="M15 12H3"/><path d="M17 18H3"/><path d="M21 6H3"/>',
  alignCenter: '<path d="M17 12H7"/><path d="M19 18H5"/><path d="M21 6H3"/>',
  alignRight: '<path d="M21 12H9"/><path d="M21 18H7"/><path d="M21 6H3"/>',
  alignJustify: '<path d="M3 12h18"/><path d="M3 18h18"/><path d="M3 6h18"/>',
  listBullet: '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>',
  listNumber: '<path d="M10 12h11"/><path d="M10 18h11"/><path d="M10 6h11"/><path d="M4 10h2"/><path d="M4 6h1v4"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>',
  outdent: '<path d="M21 12H11"/><path d="M21 18H11"/><path d="M21 6H11"/><path d="m7 8-4 4 4 4"/>',
  indent: '<path d="M21 12H11"/><path d="M21 18H11"/><path d="M21 6H11"/><path d="m3 8 4 4-4 4"/>',
  clearFormat: '<path d="M4 7V4h16v3"/><path d="M5 20h6"/><path d="M13 4 8 20"/><path d="m15 15 5 5"/><path d="m20 15-5 5"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/>',
  chevL: '<path d="m15 18-6-6 6-6"/>',
  chevR: '<path d="m9 18 6-6-6-6"/>',
  minus: '<path d="M5 12h14"/>',
  half: '<circle cx="12" cy="12" r="10"/><path d="M12 18a6 6 0 0 0 0-12v12z"/>',
  image: '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
  send: '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
  grid: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  pulse: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
  sliders: '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
  arrowLeft: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
  login: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" x2="3" y1="12" y2="12"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  dot: '<circle cx="12" cy="12" r="2.5"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
  userPlus: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" x2="19" y1="8" y2="14"/><line x1="22" x2="16" y1="11" y2="11"/>',
};
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name] || ''}</svg>`;
// Brand marks for app-style social tiles in the site footer (Simple Icons, CC0), filled on a 24×24 grid
const BRAND_ICONS = {
  telegram: 'M11.944 0m4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z',
  whatsapp: 'M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z',
  instagram: 'M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077',
  youtube: 'M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z',
  xlogo: 'M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z',
  tiktok: 'M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z',
};
const appIcon = (name) => BRAND_ICONS[name]
  ? `<svg class="app-glyph" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${BRAND_ICONS[name]}"/></svg>`
  : icon(name);

// Landing: screenshots for the hero and "How it works" (dark theme, JPEG) and the AI Detector demo video
const LANDING_MEDIA = '/static/app2/media/';
const LANDING_SHOTS = {
  dashboard: LANDING_MEDIA + 'shot-dashboard.jpg',
  check: LANDING_MEDIA + 'shot-check.jpg',
  humanize: LANDING_MEDIA + 'shot-humanize.jpg',
  format: LANDING_MEDIA + 'shot-format.jpg',
};

/* =========================================================
   Server data (templates/app_v2.html → window.DMX_BOOT)
   ========================================================= */
const BOOT = window.DMX_BOOT || {};
const API = window.DMX.api;
(function applyBoot() {
  const c = BOOT.costs || {};
  const cr = (n) => `${n} credits`;
  const item = (id) => CONFIG.groups.flatMap(g => g.items).find(i => i.id === id);
  CONFIG.signupCredits = BOOT.signupCredits ?? CONFIG.signupCredits;
  CONFIG.pricePlaceholder = 'Price shown before you pay';
  Object.assign(item('turnitin'), { price: cr(c.turnitin) });
  Object.assign(item('humanizer'), { price: cr(c.humanizer), badge: c.humanizerDiscount ? `-${c.humanizerDiscount}%` : '' });
  const fh = BOOT.freeHumanize;
  if (fh) {
    CONFIG.freeHumanize = fh;
    CONFIG.wordLimit = fh.maxWords || CONFIG.wordLimit;
    item('humanizer').guestPrice = freeHumanizeNote(false);
    const step = CONFIG.tours.humanizer.steps.find(s => s.target === '#hum-meta');
    if (step) step.textGuest = `${freeHumanizeNote(false)} without an account. A free account raises it to ${freeHumanizeNote(true).replace(/^Free: up to /, '')}.`;
  }
  Object.assign(item('workspace'), { price: `${cr(c.humanizer)} per humanize` });
  CONFIG.slides.price = cr(c.presentation);
  CONFIG.slides.perSlidePrice = c.presentationPerSlide ?? CONFIG.slides.perSlidePrice;
  Object.assign(item('presentation'), { price: `from ${cr(c.presentation + CONFIG.slides.perSlidePrice * CONFIG.slides.counts[0])}` });
  // The gallery shows the real slide themes, so the preview and the downloaded .pptx share one palette
  const sl = BOOT.slides;
  if (sl && sl.themes && sl.themes.length) {
    const hex = (v) => '#' + String(v || '').replace(/^#/, '');
    const catLabel = Object.fromEntries(sl.categories.map(l => [l.toLowerCase(), l]));
    CONFIG.slides.designCategories = sl.categories;
    CONFIG.slides.researchMaxChars = sl.researchMaxChars || CONFIG.slides.researchMaxChars;
    CONFIG.slides.designs = sl.themes.map(t => ({
      id: t.id, name: t.name, category: catLabel[t.category] || t.category, sample: t.sample_title,
      bg: hex(t.cover_bg), fg: hex(t.cover_ink), accent: hex(t.cover_accent),
      page: { bg: hex(t.bg), fg: hex(t.ink), accent: hex(t.accent), muted: hex(t.muted), pale: hex(t.pale) },
      headFont: t.web_heading_font, bodyFont: t.web_body_font, upper: !!t.heading_upper,
      photo: t.sample_image ? `/static/presentation/samples/${t.sample_image}.jpg` : '',
    }));
    const def = CONFIG.slides.designs.findIndex(d => d.id === sl.defaultTheme);
    if (def > 0) CONFIG.slides.designs.unshift(...CONFIG.slides.designs.splice(def, 1));
  }
  Object.assign(item('assignment'), { price: 'Price shown before you pay' });
  Object.assign(CONFIG.veil, { price: c.veil ?? CONFIG.veil.price, days: BOOT.veilDays ?? CONFIG.veil.days });
  CONFIG.homePage.estimates = { turnitin: c.turnitin, humanizer: c.humanizer, presentation: c.presentation };
  Object.assign(CONFIG.scan, { price: cr(c.turnitin), formats: 'DOCX, PDF or TXT', maxFileSizeMb: '16' });
  CONFIG.assignment.maxFileSizeMb = '16';
  CONFIG.format.maxFileMb = '16';
  // Appearance defaults come from the formatter's style profiles, so the preview matches the output
  const fp = BOOT.formatProfiles;
  if (fp) CONFIG.format.styles.forEach(s => {
    const form = fp[s.id];
    if (!form) return;
    const v = fmtFromBackend(form);
    ['font', 'size', 'lineSpacing', 'alignment', 'firstLineIndent', 'pageSize', 'pageNumbers', 'margins',
      'autoCaptions', 'tableCaption', 'figureCaption', 'refHeading', 'refNewPage', 'refNumbered', 'tocWordField']
      .forEach(k => { if (k in v) s.defaults[k] = v[k]; });
    if (form.margin_preset === 'custom' && form.margins) s.profileMarginIn = form.margins.left_in;
  });
  Object.assign(CONFIG.editor, { detectPrice: '1 credit / 100 words', humanizePrice: cr(c.humanizer), citePrice: cr(c.cite) });
  const cat = BOOT.catalog;
  if (cat) {
    cat.plans.forEach(sp => {
      const p = CONFIG.pricing.plans.find(x => x.id === sp.id);
      if (p) Object.assign(p, { price: sp.usd, credits: sp.credits });
    });
    Object.assign(CONFIG.pricing.payg, {
      min: cat.payg.min, max: cat.payg.max, step: cat.payg.step, baseUsd: cat.payg.base_usd, usdPerStep: cat.payg.usd_per_step,
    });
  }
  CONFIG.billing.plan = BOOT.plan ? BOOT.plan.plan_id : null;
  if (BOOT.user) {
    Object.assign(CONFIG.user, { name: BOOT.user.name, email: BOOT.user.email, id: '#' + BOOT.user.id, balance: BOOT.balance,
      isAdmin: !!BOOT.user.isAdmin });
  }
})();

/* =========================================================
   State
   ========================================================= */
CONFIG.extraItems.filter(i => i.legal).forEach(i => {
  const d = CONFIG.legal.find(x => x.id === i.id);
  i.label = d.title; i.description = d.lead;
});
const ALL_ITEMS = [CONFIG.home, ...CONFIG.groups.flatMap(g => g.items.map(i => ({ ...i, group: g.label }))), ...CONFIG.extraItems];
const ITEMS = Object.fromEntries(ALL_ITEMS.map(i => [i.id, i]));

const store = {
  get(k, d) { try { const v = localStorage.getItem('dmx-' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('dmx-' + k, JSON.stringify(v)); return true; } catch { return false; } },
};

// Documents (History on Home) are kept in this browser, one list per account
const docsKey = () => 'docs-' + (BOOT.user ? BOOT.user.id : 'guest');
const loadDocs = () => (BOOT.user ? store.get(docsKey(), []) : []);
const introKey = () => 'intro-hidden-' + (BOOT.user ? BOOT.user.id : 'guest');

const state = {
  signedIn: !!BOOT.user,
  collapsed: store.get('collapsed', false),
  drawerOpen: false,
  docs: loadDocs(),
  docFilter: 'all',
  guestRunsUsed: BOOT.guestHumanizeUsed ? 1 : 0,
  credits: [],            // Credit history, loaded from /api/economy/transactions
  usedCredits: 0,         // credits spent in the loaded history (header bar)
  theme: 'dark',                // 'dark' | 'light', saved in the browser
  balance: BOOT.balance || 0,
  returning: !!BOOT.user,
  avatarUrl: BOOT.user ? BOOT.user.avatarUrl : null,
  historyAll: false,
  creditsAll: false,       // Home: full credit history open
  profile: store.get('profile', null),   // tool picked on the landing page
  intent: null,                          // tool picked on the landing page
  editor: null,           // Editor document (title, html, zoom…)
  slides: null,           // Slides: settings, generated deck, design
  scans: [],              // AI Detector checks (filled at init)
  detMode: store.get('det-mode', 'quick'),   // AI Detector page: 'quick' (our detector) or 'turnitin'
  qd: { text: '', status: 'idle', result: null, error: '', note: '', autoRun: false, animate: false, left: null },
  scanCurrent: null,      // check shown in the result card
  scanMenu: null,         // id of the row whose ⋯ menu is open
  veil: { ...(BOOT.veil || {}) },   // { active, expiresAt } of the Veil pass
  tools: {},              // per-tool input/result state, kept while navigating
};
const toolState = (id) => state.tools[id] || (state.tools[id] = { mode: 'paste', text: '', fileName: '', status: 'idle', result: null, note: '' });

/* =========================================================
   Helpers
   ========================================================= */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtNum = (n) => n.toLocaleString('en-US').replace(/,/g, ' ');
const countWords = (t) => (t.trim().match(/\S+/g) || []).length;
const fmtDate = (iso) => new Date(iso + 'T12:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
const mobileMQ = window.matchMedia('(max-width: 768px)');
const noHoverMQ = window.matchMedia('(hover: none)');

function badgeHtml(item) {
  return (item.tag ? `<span class="tag">${esc(item.tag)}</span>` : '') +
         (item.badge ? `<span class="badge">${esc(item.badge)}</span>` : '');
}
function costHtml(item) {
  if (item.free) return '<span class="free">Free</span>';
  if (!state.signedIn && item.guestPrice) {
    return state.guestRunsUsed < 1
      ? `<span class="free">${esc(item.guestPrice)}</span>`
      : 'Today’s free runs are used — <a href="#" data-act="signup">sign up</a> for more free runs and ' + CONFIG.signupCredits + ' credits';
  }
  return esc(item.price || CONFIG.pricePlaceholder);
}
function freeHumanizeNote(signedIn) {
  const fh = CONFIG.freeHumanize;
  if (!fh) return '';
  const words = Number(signedIn ? fh.userWords : fh.guestWords).toLocaleString('en-US').replace(/,/g, ' ');
  const daily = signedIn ? fh.userDaily : fh.guestDaily;
  return `Free: up to ${words} words, ${daily} ${daily === 1 ? 'time' : 'times'} a day`;
}
function freeNoteHtml() {
  return esc(CONFIG.freeNote).replace(/\bfree\b/, '<span class="free">free</span>');
}

/* ---------- Server sync: credit history, balance, documents ---------- */
const todayIso = () => new Date().toISOString().slice(0, 10);
const saveDocs = () => { if (state.signedIn) store.set(docsKey(), state.docs.slice(0, 100)); };

const TX_LABELS = {
  humanize: ['Humanizer run', 'humanizer'], turnitin: ['AI Detector scan', 'turnitin'],
  assignment: ['Assignment', 'assignment'], presentation: ['Slides generated', 'presentation'],
  presentation_research: ['Slides web research', 'presentation'], detect: ['Editor: AI check', 'workspace'],
  check: ['Work Review', 'check'], cite: ['Citation', 'workspace'], veil: ['Veil, 30 days', 'veil'],
  topup: ['Credits top-up', null], welcome_bonus: ['Sign-up bonus', null],
  referral_signup_bonus: ['Referral bonus', 'earn'], referral_milestone: ['Referral milestone', 'earn'],
  referral_convert: ['Cashback → credits', 'earn'], admin_adjustment: ['Balance adjustment', null], admin_set: ['Balance adjustment', null],
  admin_adjust: ['Balance adjustment', null],
};
function txToCredit(tx) {
  const [label, tool] = TX_LABELS[tx.feature] || [String(tx.feature || 'Credits').replace(/_/g, ' '), null];
  const amount = Number(tx.credits ?? 0);
  return {
    id: 'tx' + tx.id, tool,
    label: tx.kind === 'refund' ? `Refund: ${label}` : label,
    date: String(tx.created_at || todayIso()).slice(0, 10),
    amount,
  };
}

async function loadCredits() {
  if (!state.signedIn) return;
  try {
    const data = await API.transactions(100);
    const monthAgo = Date.now() - 30 * 86400000;
    state.balance = Number(data.balance ?? state.balance);
    state.credits = (data.transactions || []).map(txToCredit);
    state.usedCredits = Math.max(0, (data.transactions || [])
      .filter(tx => Date.parse(String(tx.created_at || '').replace(' ', 'T')) >= monthAgo)
      .filter(tx => (tx.kind === 'debit' || tx.kind === 'refund') && !String(tx.feature || '').startsWith('admin'))
      .reduce((sum, tx) => sum - Number(tx.credits || 0), 0));
  } catch (err) {
    if (err.code === 'AUTH_REQUIRED') return onSignedOut();
  }
  renderHeader();
  if (currentRoute() === 'home' && !tour.name) rerenderHomeKeepScroll();
}

// The session ended on the server (logged out in another tab, expired)
function onSignedOut() {
  if (!state.signedIn) return;
  state.signedIn = false;
  state.credits = []; state.docs = []; state.scans = []; state.earn = null; state.billing = null; state.assign = null; state.slides = null; state.editor = null; CONFIG.billing.plan = null;
  renderSidebar(); applyLayout(); render();
}

let toastTimer;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 2800);
}

/* =========================================================
   Sidebar
   ========================================================= */
// Link to a tool: its page in the prototype, or an external page (item.url) in a new tab
const itemHref = (item) => item.url || '#/' + item.route;
const itemLinkAttrs = (item) => item.url ? 'target="_blank" rel="noopener"' : '';
const newTabNote = (item) => item.url ? '<span class="visually-hidden"> (opens in a new tab)</span>' : '';

function sidebarLogoHtml(href, where) {
  const c = isCollapsed();
  return `<a class="logo" href="${href}" ${c ? 'data-act="collapse" aria-expanded="false" aria-controls="sidebar"' : ''}
      aria-label="${c ? 'Expand menu' : `${esc(CONFIG.brand)} ${where}`}" ${c ? 'data-tip-title="Expand menu" data-tip-desc=""' : ''}>
      <span class="logo-mark">${LOGO_SVG}</span><span class="logo-text">${esc(CONFIG.brand)}</span>
    </a>`;
}
function navItemHtml(item) {
  const descId = 'desc-' + item.id;
  if (item.dialog) {
    return `<li><button type="button" class="nav-item" data-act="open-${item.dialog}" aria-haspopup="dialog"
        data-tip-title="${esc(item.label)}" data-tip-desc="${esc(item.description)}" aria-describedby="${descId}">
      ${icon(item.icon)}<span class="nav-label">${esc(item.label)}</span><span id="${descId}" hidden>${esc(item.description)}</span>
    </button></li>`;
  }
  const tipMeta = [item.tag, item.badge].filter(Boolean).join(' · ');
  return `<li>
    <a class="nav-item${item.id === 'admin' ? ' nav-admin' : ''}" href="${esc(itemHref(item))}" ${itemLinkAttrs(item)} data-route="${item.url ? '' : item.route}"
       ${item.badge ? `data-badge="${esc(item.badge)}"` : ''}
       data-tip-title="${esc(item.label)}" data-tip-desc="${esc(item.description)}" data-tip-meta="${esc(tipMeta)}"
       aria-describedby="${descId}">
      ${icon(item.icon)}
      <span class="nav-label">${esc(item.label)}${newTabNote(item)}</span>
      ${item.free && !item.info ? '<span class="nav-meta"><span class="badge">Free</span></span>' : ''}
      <span id="${descId}" hidden>${esc(item.description)}</span>
    </a>
  </li>`;
}

function themeBtnHtml() {
  const light = state.theme === 'light';
  return `<button class="icon-btn" data-act="theme" aria-label="Switch to ${light ? 'dark' : 'light'} theme"
    data-tip-title="${light ? 'Dark' : 'Light'} theme" data-tip-desc="Switch the colour theme">${icon(light ? 'moon' : 'sun')}</button>`;
}

// Theme lives on <html data-theme>; CSS swaps the HeroUI token set
function applyTheme(theme) {
  state.theme = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = state.theme;
  store.set('theme', state.theme);
}

// Money bag (Solar "Bold Duotone"), from the Figma header 153:6601
const MONEY_BAG = `<svg class="money-bag" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path opacity=".5" d="M2.11 4.78c.57-.56 1.38-.72 2.72-.76l1-.02H9.33c.3 0 .57 0 .83.002l1 .02c1.35.04 2.16.2 2.72.76.78.78.78 2.04.78 4.55s0 3.77-.78 4.55c-.78.79-2.04.79-4.55.79H6.67c-2.51 0-3.77 0-4.55-.79-.79-.78-.79-2.04-.79-4.55s0-3.77.79-4.55Z"/><path d="M8.5 6.67a.5.5 0 0 0-1 0v.003c-.73.18-1.33.76-1.33 1.55 0 .97.91 1.61 1.83 1.61.55 0 .83.36.83.61s-.28.61-.83.61-.83-.36-.83-.61a.5.5 0 0 0-1 0c0 .79.61 1.37 1.33 1.55V12a.5.5 0 0 0 1 0v-.007c.73-.18 1.33-.76 1.33-1.55 0-.97-.91-1.61-1.83-1.61-.55 0-.83-.36-.83-.61s.28-.61.83-.61.83.36.83.61a.5.5 0 0 0 1 0c0-.79-.61-1.37-1.33-1.55V6.67Z"/><path d="M8.03.83h-.07c-.6 0-1.1 0-1.5.05-.42.06-.8.19-1.1.49-.3.3-.43.68-.48 1.1-.04.28-.05.96-.05 1.55l1-.02c0-.56.01-1.17.04-1.4.04-.3.11-.44.2-.53.09-.09.22-.16.53-.2.32-.04.75-.04 1.4-.04s1.07 0 1.4.04c.3.04.43.11.52.2.09.09.16.22.2.53.03.23.04.84.04 1.4l1 .02c0-.59-.01-1.27-.05-1.55-.06-.42-.18-.8-.49-1.1-.3-.3-.68-.43-1.1-.49-.4-.05-.9-.05-1.5-.05Z"/></svg>`;

// Credits in the header, next to See Pricing (Figma 153:6601): balance, used / limit and a bar
function hdrCreditsHtml() {
  const u = { used: state.usedCredits, limit: state.usedCredits + state.balance, label: CONFIG.user.usage.label };
  const used = u.used, pct = u.limit ? Math.round(used / u.limit * 100) : 0;
  return `<button type="button" class="hdr-credits" data-act="hdr-credits" data-tip-pos="bottom"
      data-tip-title="${fmtCr(state.balance)} credits" data-tip-desc="${pct}% ${esc(u.label)} (${used} of ${u.limit}). ${esc(CONFIG.freeNote)}"
      aria-label="${fmtCr(state.balance)} credits, ${pct}% ${esc(u.label)}">
    <span class="hdr-credits-row">
      <span class="hdr-credits-amount">${MONEY_BAG}${fmtCr(state.balance)} credits</span>
      <span class="hdr-credits-count" aria-hidden="true">${pct}% used</span>
    </span>
    <span class="credit-bar" aria-hidden="true"><span style="width:${pct}%"></span></span>
  </button>`;
}

// Uploaded picture if there is one, otherwise the first letter of the name
// "Pro Plan", or "Free Plan" when there is no subscription
function planLabel() {
  const p = CONFIG.pricing.plans.find(x => x.id === CONFIG.billing.plan);
  return p ? p.name + ' Plan' : 'Free Plan';
}

function avatarInner() {
  return state.avatarUrl ? `<img src="${state.avatarUrl}" alt="">` : esc((CONFIG.user.name || '?').charAt(0).toUpperCase());
}

function profileHtml() {
  const u = CONFIG.user;
  return `<div class="profile">
    <button class="profile-btn" type="button" data-act="profile-menu" aria-haspopup="menu" aria-expanded="false" aria-controls="profile-menu"
      data-tip-title="${esc(u.name)}" data-tip-desc="${esc(planLabel())}">
      <span class="avatar" aria-hidden="true">${avatarInner()}</span>
      <span class="profile-text collapsed-hide"><span class="profile-name">${esc(u.name)}</span><span class="profile-plan">${esc(planLabel())}</span></span>
      <span class="profile-chevron collapsed-hide" aria-hidden="true">${icon('updown')}</span>
    </button>
    <div class="profile-menu" id="profile-menu" role="menu" aria-label="Account" hidden>
      ${u.menu.map((m, i) => m.admin && !u.isAdmin ? '' : `<button type="button" role="menuitem" tabindex="-1" class="${m.danger ? 'is-danger' : ''}" data-act="profile-item" data-index="${i}">${icon(m.icon)}${esc(m.label)}</button>`).join('')}
    </div>
  </div>`;
}

function toggleProfileMenu(open) {
  const menu = $('#profile-menu'), btn = $('.profile-btn');
  if (!menu) return;
  open = open ?? menu.hidden;
  menu.hidden = !open;
  btn.setAttribute('aria-expanded', String(open));
  if (open) { hideTip(); $('[role="menuitem"]', menu).focus(); }
}

// Header above every app page: greeting, credits (signed in), pricing, theme
function renderHeader() {
  const H = CONFIG.header;
  const adm = isAdminRoute() && canAdmin();
  const title = adm ? 'Admin panel' : state.signedIn ? H.greeting.replace('{name}', CONFIG.user.name) : H.guestGreeting;
  $('#app-header').innerHTML = `
    <div class="hdr-title">
      <p class="hdr-greet">${esc(title)}</p>
      <p class="hdr-sub">${esc(adm ? 'Changes here affect all users' : H.subtitle)}</p>
    </div>
    <div class="hdr-actions">
      ${state.signedIn ? hdrCreditsHtml() : ''}
      <button class="btn btn-primary hdr-pricing" type="button" data-act="pricing" aria-label="${esc(H.pricingLabel)}">
        ${icon('flash')}<span>${esc(H.pricingLabel)}</span></button>
      ${themeBtnHtml()}
    </div>`;
}

function renderSidebar() {
  const foot = state.signedIn
    ? profileHtml()
    : `<button class="btn btn-primary btn-signup btn-block" data-act="signup" aria-label="Sign up"
         data-tip-title="Sign up" data-tip-desc="Get ${CONFIG.signupCredits} free credits">
         <span aria-hidden="true" class="collapsed-hide">Sign up</span>
         <span class="signup-icon" aria-hidden="true" hidden>${icon('userPlus')}</span>
       </button>`;

  if (isAdminRoute() && canAdmin()) {
    $('#sidebar').innerHTML = adminNavHtml();
    markActive();
    renderHeader();
    return;
  }
  $('#sidebar').innerHTML = `
    <div class="sidebar-head">
      ${sidebarLogoHtml('#/home', 'home')}
      <button class="icon-btn collapse-btn" data-act="collapse"
        aria-label="${isCollapsed() ? 'Expand menu' : 'Collapse menu'}" aria-expanded="${!isCollapsed()}" aria-controls="sidebar"
        data-tip-title="${isCollapsed() ? 'Expand menu' : 'Collapse menu'}" data-tip-desc="">${icon('sidebar')}</button>
      <button class="icon-btn drawer-close" data-act="close-drawer" aria-label="Close menu">${icon('close')}</button>
    </div>
    <nav class="nav" aria-label="Tools">
      <ul>${navItemHtml(CONFIG.home)}${canAdmin() ? navItemHtml(ITEMS.admin) : ''}</ul>
      ${CONFIG.groups.map(g => `
        <div class="nav-group" role="group" aria-labelledby="grp-${g.id}">
          <div class="nav-group-label" id="grp-${g.id}">${esc(g.label)}</div>
          <ul>${g.items.map(navItemHtml).join('')}</ul>
        </div>`).join('')}
    </nav>
    <div class="sidebar-foot">${foot}</div>`;

  // In collapsed mode the Sign up button shows an icon instead of text
  const collapsed = isCollapsed();
  $$('.signup-icon').forEach(el => (el.hidden = !collapsed));
  markActive();
  renderHeader();
}

// Collapsed (icons only) only when the user collapses it; the same on every page
function isCollapsed() {
  if (mobileMQ.matches) return false;
  return state.collapsed;
}

function applyLayout() {
  const app = $('#app');
  app.classList.toggle('is-collapsed', isCollapsed());
  app.classList.toggle('drawer-open', state.drawerOpen && mobileMQ.matches);
  $('#menu-btn').setAttribute('aria-expanded', String(state.drawerOpen));
  // Hide the off-screen drawer from keyboard/screen readers on mobile
  $('#sidebar').inert = mobileMQ.matches && !state.drawerOpen;
  state.lastCollapsed = isCollapsed();
}

function markActive() {
  const route = currentRoute();
  $$('.nav-item').forEach(a => {
    if (a.dataset.route === route) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

function setDrawer(open) {
  state.drawerOpen = open;
  applyLayout();
  if (open) $('.nav-item', $('#sidebar'))?.focus();
  else $('#menu-btn').focus();
}

/* =========================================================
   Tooltip — one element in <body>, positioned with `fixed`
   so the sidebar's overflow can never clip it
   ========================================================= */
const tip = $('#tooltip');
let tipTimer = null, tipTarget = null;

function scheduleTip(el) {
  if (noHoverMQ.matches) return;          // no tooltips on touch devices
  if (el === tipTarget) return;
  hideTip();
  tipTarget = el;
  tipTimer = setTimeout(() => showTip(el), 500);
}
function showTip(el) {
  const { tipTitle, tipDesc, tipMeta } = el.dataset;
  tip.innerHTML = `<strong>${esc(tipTitle)}</strong>` +
    (tipMeta ? `<span class="tip-meta">${esc(tipMeta)}</span>` : '') +
    (tipDesc ? `<span class="tip-desc">${esc(tipDesc)}</span>` : '');
  tip.hidden = false;
  const r = el.getBoundingClientRect();
  const w = tip.offsetWidth, h = tip.offsetHeight, pad = 8;
  let left = r.right + 10;
  if (left + w > innerWidth - pad) left = Math.max(pad, r.left - w - 10);   // flip left if no room
  let top = r.top + r.height / 2 - h / 2;
  if (el.dataset.tipPos === 'bottom') {                                     // toolbars: tooltip under the button
    left = Math.min(Math.max(pad, r.left + r.width / 2 - w / 2), innerWidth - w - pad);
    top = r.bottom + 8;
  }
  top = Math.min(Math.max(pad, top), innerHeight - h - pad);
  tip.style.left = left + 'px';
  tip.style.top = top + 'px';
}
function hideTip() {
  clearTimeout(tipTimer);
  tipTarget = null;
  tip.hidden = true;
}

document.addEventListener('pointerover', (e) => {
  if (e.pointerType === 'touch') return;
  const el = e.target.closest('[data-tip-title]');
  if (el) scheduleTip(el);
});
document.addEventListener('pointerout', (e) => {
  const el = e.target.closest('[data-tip-title]');
  if (el && !el.contains(e.relatedTarget)) hideTip();
});
document.addEventListener('focusin', (e) => {
  const el = e.target.closest('[data-tip-title]');
  if (el && el.matches(':focus-visible')) scheduleTip(el);
});
document.addEventListener('focusout', (e) => { if (e.target.closest('[data-tip-title]')) hideTip(); });
document.addEventListener('pointerdown', hideTip);
$('#sidebar').addEventListener('scroll', hideTip, true);

/* =========================================================
   Router (hash based, no reload)
   ========================================================= */
function currentRoute() {
  const r = location.hash.replace(/^#\/?/, '');
  return PUBLIC_ROUTES.includes(r) || ALL_ITEMS.some(i => i.route === r) ? r : CONFIG.defaultRoute;
}
/* =========================================================
   Admin panel (menu → Admin, admins only). Its own menu replaces the
   app menu: Overview, Users, Activity, Settings, Back to app.
   Data comes from /api/admin/*; every change is recorded in Activity.
   ========================================================= */
const ADMIN_ROUTES = ['admin', 'admin-users', 'admin-activity', 'admin-settings'];
const isAdminRoute = (r = currentRoute()) => ADMIN_ROUTES.includes(r);
const canAdmin = () => state.signedIn && CONFIG.user.isAdmin;
const ADM_PAGE = 50;
const ADM_REASONS = ['Refund — tool failed', 'Support compensation', 'Promo / giveaway', 'Correction', 'Other'];

function adminState() {
  if (!state.adm) {
    state.adm = {
      ov: null, users: null, detail: null, feed: null, pre: null, data: null,
      loading: {}, err: {}, tick: {}, loadedAt: 0,
      period: 'today', excl: true,
      uFilter: 'all', uQuery: '', uOffset: 0, selId: null, uTab: 'overview', mode: 'add', amount: 50,
      done: null, undo: null, lastReason: ADM_REASONS[0], busy: false,
      aCat: 'all', aQuery: '', hideBots: true, hideStaff: true, openId: null, older: false,
      draft: null, topup: 500, sess: null, savedMsg: false, saving: false,
    };
  }
  return state.adm;
}
const admFmt = (n) => Number(n || 0).toLocaleString('en-US');

const ADM_LOAD = {
  ov: () => API.admin.overview(),
  users: (s) => API.admin.users({ q: s.uQuery.trim(), filter: s.uFilter, offset: s.uOffset, limit: ADM_PAGE }),
  detail: (s) => API.admin.user(s.selId),
  feed: (s) => API.admin.activity({ cat: s.aCat, q: s.aQuery.trim(), hide_bots: s.hideBots ? 1 : 0, hide_staff: s.hideStaff ? 1 : 0 }),
  pre: () => API.admin.preflight(false),
  data: () => API.admin.datasetStats(),
};
// Fetch one admin dataset; the latest request for the same key wins. Old data stays on screen meanwhile.
async function admLoad(key) {
  const s = adminState(), t = (s.tick[key] = (s.tick[key] || 0) + 1);
  s.loading[key] = true; s.err[key] = null;
  let data = null, err = null;
  try { data = await ADM_LOAD[key](s); } catch (e) { err = e; }
  if (state.adm !== s || t !== s.tick[key]) return;
  s.loading[key] = false;
  if (err) s.err[key] = err.message || 'Could not load.';
  else { s[key] = data; if (key === 'ov') s.loadedAt = Date.now(); }
  if (isAdminRoute() && canAdmin()) rerenderAdmin();
}
// Called while rendering: start loading what the page needs, once
function admNeed(...keys) {
  const s = adminState();
  keys.forEach(k => {
    if (s[k] || s.loading[k] || s.err[k]) return;
    s.loading[k] = true;
    setTimeout(() => admLoad(k));
  });
}
function admPending(key, label) {
  const s = adminState();
  if (s.err[key]) return `<div class="card adm-card"><div class="empty" role="alert"><strong>Couldn’t load ${esc(label)}</strong>${esc(s.err[key])}
    <br><br><button class="btn btn-sm" data-act="adm-retry" data-v="${key}">Try again</button></div></div>`;
  return `<div class="card adm-card"><div class="empty" role="status">Loading ${esc(label)}…</div></div>`;
}
const admUpdated = (at) => {
  const min = Math.floor((Date.now() - at) / 60000);
  return min < 1 ? 'Updated just now' : `Updated ${min} min ago`;
};
// Services that need attention (from the preflight check)
function admServiceIssues() {
  const pre = adminState().pre;
  return pre ? (pre.checks || []).filter(c => c.required && !c.ok) : [];
}

// Admin menu shown instead of the app menu
function adminNavHtml() {
  const s = adminState(), r = currentRoute();
  admNeed('ov', 'pre');
  const alerts = s.ov ? s.ov.alerts.length : 0;
  const issues = admServiceIssues();
  const item = (route, ic, label, meta = '') => `<li><a class="nav-item" href="#/${route}" data-route="${route}" ${route === r ? 'aria-current="page"' : ''}
      data-tip-title="${label}" data-tip-desc="">${icon(ic)}<span class="nav-label">${label}</span>${meta}</a></li>`;
  return `
    <div class="sidebar-head">
      <a class="logo" href="#/admin" aria-label="${esc(CONFIG.brand)} admin">
        <span class="logo-mark">${LOGO_SVG}</span><span class="logo-text">${esc(CONFIG.brand)}</span>
      </a>
      <button class="icon-btn collapse-btn" data-act="collapse" aria-label="${isCollapsed() ? 'Expand menu' : 'Collapse menu'}" aria-expanded="${!isCollapsed()}" aria-controls="sidebar"
        data-tip-title="${isCollapsed() ? 'Expand menu' : 'Collapse menu'}" data-tip-desc="">${icon('sidebar')}</button>
      <button class="icon-btn drawer-close" data-act="close-drawer" aria-label="Close menu">${icon('close')}</button>
    </div>
    <nav class="nav" aria-label="Admin">
      <ul><li><a class="nav-item" href="#/home" data-tip-title="Back to app" data-tip-desc="">${icon('arrowLeft')}<span class="nav-label">Back to app</span></a></li></ul>
      <div class="nav-group" role="group" aria-labelledby="grp-admin">
      <div class="nav-group-label" id="grp-admin">Admin panel</div>
      <ul>
        ${item('admin', 'grid', 'Overview', alerts ? `<span class="nav-meta"><span class="adm-count" aria-label="${alerts} alerts">${alerts}</span></span>` : '')}
        ${item('admin-users', 'users', 'Users', s.ov ? `<span class="nav-meta small muted">${admFmt(s.ov.totals.all)}</span>` : '')}
        ${item('admin-activity', 'pulse', 'Activity')}
        ${item('admin-settings', 'sliders', 'Settings')}
      </ul>
      </div>
    </nav>
    <div class="sidebar-foot">
      <p class="adm-health collapsed-hide">${!s.pre ? '<span class="adm-dot" aria-hidden="true"></span>Checking services…'
        : issues.length ? `<span class="adm-dot red" aria-hidden="true"></span>${issues.length} service${issues.length > 1 ? 's' : ''} need attention`
        : '<span class="adm-dot ok" aria-hidden="true"></span>All services OK'}</p>
      ${profileHtml()}
    </div>`;
}

function adminHead(title, sub, right = '') {
  return `<header class="adm-head"><div><h1>${esc(title)}</h1><p class="muted small">${sub}</p></div>${right}</header>`;
}
const admSwitch = (act, on, label) => `<button class="adm-switch" role="switch" aria-checked="${on}" data-act="${act}"><span class="adm-track" aria-hidden="true"><span></span></span>${label}</button>`;
const admAlertBtn = (a) => a.href
  ? `<a class="btn btn-sm" href="${esc(a.href)}">${esc(a.cta)}</a>`
  : `<button class="btn btn-sm ${a.level === 'red' ? 'btn-danger' : ''}" data-act="adm-go" data-to="${a.to}" data-cat="${a.cat || ''}" data-filter="${a.filter || ''}" data-anchor="${a.anchor || ''}">${esc(a.cta)}</button>`;

/* ---------- Overview ---------- */
function renderAdminOverview() {
  const s = adminState();
  admNeed('ov', 'pre');
  const periods = [['today', 'Today'], ['d7', '7 days'], ['d30', '30 days'], ['all', 'All time']];
  const right = `<div class="adm-head-actions">${admSwitch('adm-excl', s.excl, 'Exclude staff &amp; test')}
        <div class="seg" role="tablist" aria-label="Period">${periods.map(([k, l]) => `<button role="tab" aria-selected="${k === s.period}" data-act="adm-period" data-v="${k}">${l}</button>`).join('')}</div>
        <button class="icon-btn" data-act="adm-refresh" aria-label="Refresh" data-tip-title="Refresh" data-tip-desc="" ${s.loading.ov ? 'disabled' : ''}>${icon('refresh')}</button></div>`;
  const sub = `${s.loadedAt ? admUpdated(s.loadedAt) + ' · ' : ''}Daily counters reset at 00:00 Tashkent time`;
  if (!s.ov) return `<div class="page adm-page">${adminHead('Overview', sub, right)}${admPending('ov', 'the overview')}</div>`;
  const O = s.ov, d = O.periods[s.period], ex = s.excl, hn = O.hiddenNote;
  const fl = d.f[ex ? 0 : 1], max = Math.max(1, ...fl.map(x => x[1]));
  const today = O.today || {}, limit = Number(today.humanizer_daily_limit || 0), left = Math.max(0, Number(today.humanizer_remaining ?? limit));
  const pool = Number((O.settings || {}).turnitin_global_balance || 0);
  const issues = admServiceIssues(), checks = s.pre ? (s.pre.checks || []).length : 0;
  const disc = O.discount || {};
  const hiddenWho = [hn.staff && `${hn.staff} staff`, hn.test && `${hn.test} test account${hn.test > 1 ? 's' : ''}`].filter(Boolean).join(' and ');
  return `<div class="page adm-page">
    ${adminHead('Overview', sub, right)}

    <section aria-labelledby="adm-att-h" class="adm-block">
      <h2 id="adm-att-h" class="adm-label">Needs attention · ${O.alerts.length}</h2>
      ${O.alerts.length ? `<ul class="adm-alerts">${O.alerts.map(a => `<li class="adm-alert ${a.level}" ${a.level === 'red' ? 'role="alert"' : ''}>
          <span class="adm-dot ${a.level}" aria-hidden="true"></span>
          <div><p class="adm-alert-t">${esc(a.title)}</p><p class="small muted">${esc(a.text)}</p></div>
          ${admAlertBtn(a)}
        </li>`).join('')}</ul>` : '<p class="small muted">Nothing needs your attention right now.</p>'}
      <p class="adm-okline small muted">
        <span>${O.withdrawalsPending ? `<span class="adm-dot amber" aria-hidden="true"></span><a href="/admin?classic=1#withdrawals">${O.withdrawalsPending} withdrawal request${O.withdrawalsPending > 1 ? 's' : ''}</a>`
          : '<span class="adm-dot ok" aria-hidden="true"></span>No withdrawal requests'}</span>
        <span>${!s.pre ? '<span class="adm-dot" aria-hidden="true"></span>Checking AI services…'
          : issues.length ? `<span class="adm-dot red" aria-hidden="true"></span><a href="#/admin-settings" data-act="adm-go" data-to="admin-settings" data-anchor="adm-services">${issues.length} AI service${issues.length > 1 ? 's' : ''} need attention</a>`
          : `<span class="adm-dot ok" aria-hidden="true"></span>All ${checks} AI services OK`}</span>
        <span>${disc.active ? `<span class="badge">−${disc.percent}%</span> Humanizer discount live${disc.source === 'auto' ? ' (auto)' : ''}` : 'Humanizer discount off'}</span>
      </p>
    </section>

    <section aria-label="Key numbers" class="adm-block">
      <div class="adm-kpis">${d.k.map(k => `<div class="card adm-kpi">
          <p class="small muted">${esc(k[0])}</p><p class="adm-kpi-v">${esc(ex ? k[1] : k[2])}</p>
          <p class="small ${!ex ? 'muted' : k[4] > 0 ? 'adm-up' : k[4] < 0 ? 'adm-down' : 'muted'}">${esc(ex ? k[3] : 'Includes staff & test')}</p>
        </div>`).join('')}</div>
      <p class="small muted">${!ex ? 'Showing everyone, including staff and test accounts.'
        : hiddenWho ? `Real users only. ${hiddenWho} are hidden — they made ${hn.share}% of all credit usage.` : 'Real users only.'}</p>
    </section>

    <div class="adm-two">
      <section class="card adm-card" aria-labelledby="adm-lim-h">
        <div class="adm-card-head"><h2 id="adm-lim-h">Service limits</h2><a href="#/admin-settings">Manage</a></div>
        <div class="adm-meter">
          <p><span>Humanizer · today</span><span class="muted"><b>${admFmt(left)}</b> of ${admFmt(limit)} left</span></p>
          <div class="credit-bar adm-bar-ok" role="progressbar" aria-label="Humanizer requests left today" aria-valuemin="0" aria-valuemax="${limit}" aria-valuenow="${left}"><span style="width:${limit ? Math.round(left / limit * 100) : 0}%"></span></div>
          <p class="small muted">Resets at 00:00</p>
        </div>
        <div class="adm-meter">
          <p><span>Turnitin pool</span><span class="${pool ? 'muted' : 'adm-red'}"><b>${admFmt(pool)}</b> left</span></p>
          <div class="credit-bar adm-bar-ok" aria-hidden="true"><span style="width:${Math.min(100, pool / 10)}%"></span></div>
          <p class="small muted">Shared pool · doesn’t reset</p>
        </div>
      </section>
      <section class="card adm-card adm-wide" aria-labelledby="adm-feat-h">
        <div class="adm-card-head"><h2 id="adm-feat-h">Feature usage</h2><span class="small muted">runs · ${esc(d.label)}</span></div>
        <ul class="adm-bars">${fl.map(([n, v]) => `<li><span>${esc(n)}</span><span class="adm-barline" aria-hidden="true"><span style="width:${v ? Math.max(3, Math.round(v / max * 100)) : 0}%"></span></span><b>${admFmt(v)}</b></li>`).join('')}</ul>
      </section>
    </div>

    <section class="card adm-card" aria-labelledby="adm-latest-h">
      <div class="adm-card-head"><h2 id="adm-latest-h">Latest from real users</h2><a href="#/admin-activity">All activity</a></div>
      ${O.latest.length ? `<div class="table-wrap adm-flat"><table class="adm-table"><tbody>${O.latest.map(a => `<tr><td class="muted adm-time">${esc(a[0])}</td><td>${esc(a[1])}</td><td class="muted adm-right">${esc(a[2])}</td></tr>`).join('')}</tbody></table></div>`
        : '<p class="small muted">No activity from real users yet.</p>'}
    </section>
  </div>`;
}

/* ---------- Users ---------- */
const ADM_FLAGS = { susp: 'Suspicious', staff: 'Staff', test: 'Test', blocked: 'Blocked' };
const admChip = (f) => f ? `<span class="adm-flag ${f}">${ADM_FLAGS[f]}</span>` : '';
const admInitial = (u) => (u.name === '—' ? u.email : u.name).charAt(0).toUpperCase();
const admIsSelf = (u) => CONFIG.user.id === '#' + u.id;
function admSelUser() {
  const s = adminState();
  if (!s.selId) return null;
  if (s.detail && s.detail.user.id === s.selId) return s.detail.user;
  return (s.users ? s.users.users : []).find(u => u.id === s.selId) || null;
}

function renderAdminUsers() {
  const s = adminState();
  admNeed('users');
  const U = s.users, counts = U ? U.counts : {}, t = U ? U.totals : null;
  const fdefs = [['all', 'All', counts.all], ['susp', 'Suspicious', counts.susp], ['staff', 'Staff & test', counts.staff], ['zero', '0 credits', counts.zero], ['new', 'New this week', counts.new]];
  const list = U ? U.users : [];
  const suspLeft = s.uFilter === 'susp' ? list.filter(u => u.flag === 'susp') : [];
  const sel = admSelUser();
  const sub = t ? `${admFmt(t.all)} accounts · ${admFmt(t.real)} real · ${t.staff} staff · ${t.test} test` : 'Loading…';
  const body = !U
    ? `<tr><td colspan="5" class="muted adm-empty">${s.err.users ? `${esc(s.err.users)} <button class="link-btn" data-act="adm-retry" data-v="users">Try again</button>` : 'Loading users…'}</td></tr>`
    : list.map(u => `<tr class="${u.id === s.selId ? 'is-sel' : ''} ${u.blocked ? 'is-blocked' : ''}">
            <td><div class="adm-user"><span class="avatar" aria-hidden="true">${esc(admInitial(u))}</span>
              <div><button class="adm-link" data-act="adm-open" data-id="${u.id}">${esc(u.name)}</button><span class="small muted">${esc(u.email)} · #${u.id}</span></div></div></td>
            <td class="adm-right ${u.credits === 0 ? 'adm-amber' : ''}">${admFmt(u.credits)}</td>
            <td>${admChip(u.flag)}</td><td class="muted">${esc(u.joined)}</td><td class="muted">${esc(u.last)}</td>
          </tr>`).join('') || `<tr><td colspan="5" class="muted adm-empty">No users match.</td></tr>`;
  const from = U && U.total ? U.offset + 1 : 0, to = U ? U.offset + list.length : 0;
  return `<div class="page adm-page adm-users ${sel ? 'has-drawer' : ''}">
    <div class="adm-users-main">
      ${adminHead('Users', sub, `<a class="btn" href="${API.admin.usersCsvUrl}" download>${icon('download')} Export CSV</a>`)}
      <div class="adm-tools">
        <label class="adm-search"><span class="visually-hidden">Search users</span>${icon('search')}
          <input type="search" id="adm-u-q" placeholder="Email, name, ID or IP" value="${esc(s.uQuery)}" autocomplete="off"></label>
        <div class="adm-chips" role="group" aria-label="Filter users">${fdefs.map(([k, l, n]) => `<button class="adm-chip" aria-pressed="${k === s.uFilter}" data-act="adm-ufilter" data-v="${k}">${l}${n === undefined ? '' : ` <span>${admFmt(n)}</span>`}</button>`).join('')}</div>
      </div>
      ${s.uFilter === 'susp' ? `<div class="adm-warn"><div><p class="adm-alert-t">These accounts look like welcome-bonus farming</p>
          <p class="small muted">Flagged for disposable email domains, shared IPs, the same device or look-alike emails. Check before blocking — flags can be wrong.</p></div>
          <button class="btn btn-sm btn-warn" data-act="adm-block-all" ${suspLeft.length && !s.busy ? '' : 'disabled'}>${suspLeft.length ? `Block all ${suspLeft.length}` : 'None left'}</button></div>` : ''}
      <div class="table-wrap"><table class="adm-table adm-users-table">
        <thead><tr><th scope="col">User</th><th scope="col" class="adm-right">Credits</th><th scope="col">Flags</th><th scope="col">Joined ↓</th><th scope="col">Last active</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
      <div class="adm-pager small muted"><span>${U ? (U.total ? `${from}–${to} of ${admFmt(U.total)}` : '0 shown') : ''}</span>
        <span><button class="icon-btn adm-pg" aria-label="Previous page" data-act="adm-prev" ${U && U.offset > 0 ? '' : 'disabled'}>${icon('arrowLeft')}</button><button class="icon-btn adm-pg" aria-label="Next page" data-act="adm-next" ${U && to < U.total ? '' : 'disabled'}>${icon('arrow')}</button></span></div>
      </div>
    </div>
    ${sel ? adminDrawerHtml(sel) : ''}
  </div>`;
}

function adminDrawerHtml(u) {
  const s = adminState(), f = u.flag, bal = u.credits;
  const det = s.detail && s.detail.user.id === u.id ? s.detail : null;
  const delta = s.mode === 'add' ? s.amount : -Math.min(s.amount, bal);
  const after = bal + delta;
  const tabs = [['overview', 'Overview'], ['history', 'Credits history'], ['purchases', 'Purchases']];
  const self = admIsSelf(u), protectedUser = self || u.isAdmin;
  const row = (t, sub, btn) => `<div class="adm-acc-row"><div><p>${t}</p><p class="small muted">${sub}</p></div>${btn}</div>`;
  const signed = (n) => (n > 0 ? '+' : n < 0 ? '−' : '') + admFmt(Math.abs(n));
  const wait = s.busy ? 'disabled' : '';
  const loadingBox = s.err.detail ? `<p class="small adm-red">${esc(s.err.detail)} <button class="link-btn" data-act="adm-retry" data-v="detail">Try again</button></p>` : '<p class="small muted" role="status">Loading…</p>';
  const markRow = u.isAdmin
    ? row('Hidden from analytics', 'Admins never count as real users', '')
    : u.accountFlag
      ? row(`Marked as ${u.accountFlag}`, 'Hidden from analytics', `<button class="btn btn-sm" data-act="adm-flag" data-v="" ${wait}>Unmark</button>`)
      : row('Mark as staff / test', 'Hidden from analytics', `<span class="adm-row"><button class="btn btn-sm" data-act="adm-flag" data-v="staff" ${wait}>Staff</button><button class="btn btn-sm" data-act="adm-flag" data-v="test" ${wait}>Test</button></span>`);
  return `<aside class="adm-drawer" aria-labelledby="adm-d-name">
    <div class="adm-d-head">
      <span class="avatar adm-avatar-lg" aria-hidden="true">${esc(admInitial(u))}</span>
      <div><p class="adm-d-name" id="adm-d-name">${esc(u.name)} ${admChip(f)}${u.isAdmin ? ' <span class="adm-flag staff">Admin</span>' : ''}</p><p class="small muted">${esc(u.email)}</p>
        <p class="small muted">#${u.id} · joined ${esc(u.joined)}${u.ip ? ` · <code>${esc(u.ip)}</code>` : ''}</p></div>
      <button class="icon-btn" data-act="adm-close" aria-label="Close details">${icon('close')}</button>
    </div>
    ${f === 'susp' ? `<div class="adm-warn adm-warn-col"><p class="adm-alert-t">Why it’s flagged</p>
        <ul>${(u.reasons || []).map(r => `<li>${esc(r)}</li>`).join('')}</ul>
        <div class="adm-row"><button class="btn btn-sm btn-warn" data-act="adm-block" data-bonus="1" ${wait}>Block &amp; remove bonus</button><button class="btn btn-sm" data-act="adm-clear" ${wait}>Not suspicious</button></div></div>` : ''}
    ${u.blocked ? `<div class="adm-note" role="status"><span>Blocked · can’t sign in or use credits</span><button class="link-btn" data-act="adm-unblock" ${wait}>Unblock</button></div>` : ''}
    <div class="adm-tabs" role="tablist" aria-label="User sections">${tabs.map(([k, l]) => `<button role="tab" aria-selected="${k === s.uTab}" data-act="adm-utab" data-v="${k}">${l}</button>`).join('')}</div>
    ${s.uTab === 'overview' ? `
      <div class="adm-stats">
        <div><p class="small muted">Balance</p><p class="adm-stat">${admFmt(bal)}</p></div>
        <div><p class="small muted">Spent</p><p class="adm-stat">${admFmt(u.spent)}</p></div>
        <div><p class="small muted">Paid</p><p class="adm-stat">${det ? '$' + admFmt(det.paidUsd) : '…'}</p></div>
      </div>
      <section class="adm-box" aria-labelledby="adm-adj-h">
        <h3 id="adm-adj-h">Adjust credits</h3>
        ${s.done ? `<div class="adm-ok" role="status"><span>${esc(s.done)}</span>${s.undo ? `<button class="link-btn" data-act="adm-undo" ${wait}>Undo</button>` : ''}</div>` : ''}
        <div class="seg adm-seg" role="radiogroup" aria-label="Add or remove">
          <button role="radio" aria-checked="${s.mode === 'add'}" aria-selected="${s.mode === 'add'}" data-act="adm-mode" data-v="add">+ Add</button>
          <button role="radio" aria-checked="${s.mode === 'remove'}" aria-selected="${s.mode === 'remove'}" data-act="adm-mode" data-v="remove">− Remove</button></div>
        <div class="adm-chips" role="group" aria-label="Amount">${[10, 50, 100, 500].map(a => `<button class="adm-chip adm-amt" aria-pressed="${a === s.amount}" data-act="adm-amount" data-v="${a}">${s.mode === 'add' ? '+' : '−'}${a}</button>`).join('')}</div>
        <label class="field" for="adm-reason"><span>Reason (saved to Activity)</span>
          <select class="select" id="adm-reason">${ADM_REASONS.map(r => `<option ${r === s.lastReason ? 'selected' : ''}>${r}</option>`).join('')}</select></label>
        <p class="adm-newbal"><span class="muted">New balance</span><span>${admFmt(bal)} → <b class="${delta >= 0 ? 'adm-up' : 'adm-down'}">${admFmt(after)}</b></span></p>
        <button class="btn btn-primary btn-block" data-act="adm-apply" ${s.busy || !delta ? 'disabled' : ''}>${s.mode === 'add' ? 'Add' : 'Remove'} ${admFmt(Math.abs(delta))} credits</button>
      </section>
      <section class="adm-box" aria-labelledby="adm-acc-h">
        <h3 id="adm-acc-h">Account</h3>
        ${markRow}
        ${protectedUser ? row('Block account', self ? 'You can’t block yourself' : 'Remove admin access first', '')
          : row('Block account', u.blocked ? 'Blocked — can’t sign in' : 'Can’t sign in. You can undo it.', `<button class="btn btn-sm" data-act="${u.blocked ? 'adm-unblock' : 'adm-block'}" ${wait}>${u.blocked ? 'Unblock' : 'Block'}</button>`)}
        <hr>
        ${self ? row('Admin access', 'This is your account', '')
          : row('Admin access', u.isAdmin ? 'Has full control of credits, prices, users' : 'Full control of credits, prices, users', `<button class="btn btn-sm" data-act="adm-role" ${wait}>${u.isAdmin ? 'Remove admin…' : 'Make admin…'}</button>`)}
        ${protectedUser ? '' : row('<span class="adm-red">Delete account</span>', 'Permanent. History stays in Activity.', `<button class="btn btn-sm btn-danger-soft" data-act="adm-delete" ${wait}>Delete…</button>`)}
      </section>` : ''}
    ${s.uTab === 'history' ? (det ? `${det.ledger.length ? `<ul class="adm-ledger">${det.ledger.map(l => `<li><div><p>${esc(l.label)}</p><p class="small muted">${esc(l.when)}</p></div>
        <div class="adm-right"><p class="${l.amount > 0 ? 'adm-up' : ''}">${signed(l.amount)}</p><p class="small muted">bal. ${admFmt(l.balance)}</p></div></li>`).join('')}</ul>` : '<div class="empty">No credit movements yet.</div>'}
      <a href="#/admin-activity" data-act="adm-go" data-to="admin-activity" data-q="#${u.id}">Open all activity for this user</a>` : loadingBox) : ''}
    ${s.uTab === 'purchases' ? (det ? (det.purchases.length
        ? `<ul class="adm-ledger">${det.purchases.map(p => `<li><div><p>${esc(p.item || 'Purchase')}</p><p class="small muted">${esc(p.date || '')}</p></div>
          <div class="adm-right"><p>${p.amount != null ? '$' + esc(p.amount) : ''}</p><p class="small muted">${esc(p.status || '')}</p></div></li>`).join('')}</ul>`
        : `<div class="empty"><strong>No purchases yet</strong>${det.checkoutOpens ? `Opened checkout ${det.checkoutOpens} time${det.checkoutOpens > 1 ? 's' : ''}, didn’t pay.` : 'Never opened checkout.'}</div>`) : loadingBox) : ''}
  </aside>`;
}

/* ---------- Activity ---------- */
function renderAdminActivity() {
  const s = adminState();
  admNeed('feed');
  const F = s.feed;
  const cats = [['all', 'All'], ['credits', 'Credits & tools'], ['auth', 'Sign-ups & logins'], ['admin', 'Admin actions'], ['error', 'Errors']];
  const errCount = F ? F.errorsToday : 0;
  const hidden = [s.hideBots && (F && F.hiddenBots ? `${admFmt(F.hiddenBots)} bot request${F.hiddenBots > 1 ? 's' : ''}` : 'bots'), s.hideStaff && 'staff & test'].filter(Boolean);
  const ICO = { auth: 'login', credits: 'sparkles', error: 'alert', admin: 'shield', bot: 'dot' };
  const events = F ? F.events : [];
  const days = [...new Set(events.map(e => e.day))];
  const feed = !F
    ? `<div class="empty" role="status">${s.err.feed ? `${esc(s.err.feed)}<br><br><button class="btn btn-sm" data-act="adm-retry" data-v="feed">Try again</button>` : 'Loading activity…'}</div>`
    : days.map(day => `<p class="adm-day">${esc(day)}</p>
        <ul>${events.filter(e => e.day === day).map(e => {
          const open = s.openId === e.id;
          return `<li class="adm-ev ${open ? 'open' : ''}">
            <button class="adm-ev-row" data-act="adm-ev" data-id="${e.id}" aria-expanded="${open}">
              <span class="muted adm-time">${esc(e.time)}</span>
              <span class="adm-ev-ico ${e.cat}" aria-hidden="true">${icon(ICO[e.cat] || 'dot')}</span>
              <span class="adm-ev-text"><span>${esc(e.text)}${e.times > 1 ? ` <span class="adm-x">×${e.times}</span>` : ''}${e.staff ? ' <span class="adm-flag staff">Staff</span>' : ''}</span>
                ${e.sub ? `<span class="small ${e.cat === 'error' ? 'adm-red' : 'muted'}">${esc(e.sub)}</span>` : ''}</span>
              <span class="adm-amt ${e.amt.startsWith('+') ? 'adm-up' : e.amt === 'free' ? 'muted' : ''}">${esc(e.amt)}</span>
              <span class="adm-ev-user">${esc(e.user)}</span>
            </button>
            ${open ? `<dl class="adm-raw">${e.email ? `<dt>User</dt><dd>${esc(e.email)}</dd>` : ''}<dt>Request</dt><dd><code>${esc(e.raw)}</code></dd><dt>IP</dt><dd><code>${esc(e.ip || '—')}</code></dd><dt>Time</dt><dd>${esc(e.date)} · ${esc(e.time)} GMT+5</dd></dl>` : ''}
          </li>`;
        }).join('')}</ul>`).join('') || '<div class="empty">Nothing here with these filters.</div>';
  return `<div class="page adm-page">
    ${adminHead('Activity', 'What happened on the site. One action = one line.',
      `<button class="icon-btn" data-act="adm-refresh" data-v="feed" aria-label="Refresh" data-tip-title="Refresh" data-tip-desc="" ${s.loading.feed ? 'disabled' : ''}>${icon('refresh')}</button>`)}
    <div class="adm-tools">
      <label class="adm-search"><span class="visually-hidden">Search activity</span>${icon('search')}
        <input type="search" id="adm-a-q" placeholder="#ID, email, IP or text" value="${esc(s.aQuery)}" autocomplete="off"></label>
      <div class="adm-chips" role="group" aria-label="Category">${cats.map(([k, l]) => `<button class="adm-chip" aria-pressed="${k === s.aCat}" data-act="adm-acat" data-v="${k}">${l}${k === 'error' && errCount ? ` <span class="adm-count" aria-label="${errCount} today">${errCount}</span>` : ''}</button>`).join('')}</div>
    </div>
    <div class="adm-toggles">${admSwitch('adm-bots', s.hideBots, 'Hide bots &amp; technical requests')}${admSwitch('adm-staff', s.hideStaff, 'Hide staff &amp; test')}
      <span class="small muted">${hidden.length ? 'Hidden: ' + hidden.join(', ') : 'Showing everything'}</span></div>
    <div class="card adm-feed">
      ${feed}
      ${F && F.nextOffset != null ? `<div class="adm-more"><button class="btn btn-sm" data-act="adm-older" ${s.older ? 'disabled' : ''}>${s.older ? 'Loading…' : 'Load older'}</button></div>` : ''}
    </div>
  </div>`;
}

/* ---------- Settings ---------- */
// What is saved on the server, in the page's terms
function admSaved() {
  const S = (adminState().ov || {}).settings || {};
  return {
    mode: S.is_humanizer_discount_active ? 'manual' : S.auto_discount_enabled ? 'auto' : 'off',
    percent: Number(S.humanizer_discount_percent ?? 50), humLimit: Number(S.humanizer_daily_limit ?? 50),
    pool: Number(S.turnitin_global_balance || 0), autoTime: S.auto_discount_time || '20:00',
    autoMin: Number(S.auto_discount_min_remaining ?? 10), poolAdd: 0,
  };
}
function renderAdminSettings() {
  const s = adminState();
  admNeed('ov', 'pre', 'data');
  const anchors = (red) => `<nav class="adm-chips" aria-label="On this page">
        <a class="adm-chip" href="#adm-discount" data-act="adm-anchor" data-v="adm-discount">Discount</a>
        <a class="adm-chip" href="#adm-limits" data-act="adm-anchor" data-v="adm-limits">Limits${red ? '<span class="adm-dot red" aria-label="needs attention"></span>' : ''}</a>
        <a class="adm-chip" href="#adm-services" data-act="adm-anchor" data-v="adm-services">AI services</a>
        <a class="adm-chip" href="#adm-data" data-act="adm-anchor" data-v="adm-data">Training data</a></nav>`;
  if (!s.ov) return `<div class="page adm-page adm-settings"><header class="adm-head"><div><h1>Settings</h1>${anchors(false)}</div></header>${admPending('ov', 'settings')}</div>`;
  const sv = admSaved(), v = { ...sv, ...(s.draft || {}) }, pool = sv.pool + v.poolAdd;
  const changes = [];
  if (v.mode !== sv.mode || v.percent !== sv.percent || v.autoTime !== sv.autoTime || v.autoMin !== sv.autoMin) changes.push('discount');
  if (v.humLimit !== sv.humLimit) changes.push('daily limit');
  if (v.poolAdd) changes.push(`+${admFmt(v.poolAdd)} Turnitin checks`);
  const modes = [['off', 'Off', 'Full price, no badge'], ['manual', 'Manual', 'On until you turn it off'], ['auto', 'Auto', 'Evenings, if capacity is left']];
  const hints = { off: 'Everyone pays full price.', manual: 'Stays on until you switch it off.', auto: 'Sells unused Humanizer capacity in the evening. Off at midnight.' };
  const used = Number((s.ov.today || {}).humanizer_requests_count || 0);
  const sw = s.sess;
  const sess = !sw ? ['Not checked yet · opens the StealthWriter tab, doesn’t humanize', 'Not checked', 'amber']
    : sw === 'checking' ? ['Opening StealthWriter tab…', 'Checking…', 'muted']
    : sw.ok ? [`${sw.detail} · checked just now`, 'OK', 'ok'] : [sw.detail, 'Problem', 'red'];
  const poolState = pool === 0 ? ['Empty — checks are failing', 'red'] : pool < 50 ? ['Running low', 'amber'] : ['OK', 'ok'];
  const services = s.pre ? (s.pre.checks || []).filter(c => c.id !== 'stealthwriter') : null;
  const D = s.data;
  return `<div class="page adm-page adm-settings">
    <header class="adm-head"><div><h1>Settings</h1>${anchors(sv.pool === 0)}</div></header>

    <section class="card adm-card" id="adm-discount" aria-labelledby="adm-disc-h">
      <div class="adm-card-head"><div><h2 id="adm-disc-h">Humanizer discount</h2><p class="muted small">${hints[v.mode]}</p></div>
        <span class="lvl ${sv.mode === 'off' ? 'lvl-medium' : 'lvl-low'}">${sv.mode === 'off' ? 'Off' : `${s.ov.discount && s.ov.discount.active ? 'Live' : 'Waiting'} · −${sv.percent}% (${sv.mode})`}</span></div>
      <div class="adm-modes" role="radiogroup" aria-label="Discount mode">${modes.map(([k, l, sub]) => `<button class="adm-mode" role="radio" aria-checked="${k === v.mode}" data-act="adm-set" data-k="mode" data-v="${k}"><b>${l}</b><span class="small muted">${sub}</span></button>`).join('')}</div>
      ${v.mode !== 'off' ? `<div class="adm-row adm-end">
        <div><p class="small muted">Discount</p><div class="adm-chips">${[10, 25, 50, 70].map(p => `<button class="adm-chip adm-amt" aria-pressed="${p === v.percent}" data-act="adm-set" data-k="percent" data-v="${p}">${p}%</button>`).join('')}</div></div>
        <div><p class="small muted">Users will see</p><p class="adm-preview">Humanizer <span class="badge">−${v.percent}%</span></p></div></div>` : ''}
      ${v.mode === 'auto' ? `<div class="adm-auto">
        <p>Turn on after <label><span class="visually-hidden">Trigger time</span><input class="field-input" type="time" id="adm-auto-time" value="${esc(v.autoTime)}"></label> if at least
          <label><span class="visually-hidden">Minimum requests left</span><input class="field-input adm-num" type="number" id="adm-auto-min" value="${v.autoMin}" min="0"></label> requests are left today</p>
        <p class="small muted">Turns off at 00:00. Today ${admFmt(Math.max(0, v.humLimit - used))} are left.</p></div>` : ''}
    </section>

    <section class="card adm-card" id="adm-limits" aria-labelledby="adm-lim2-h">
      <h2 id="adm-lim2-h">Service limits</h2>
      <div class="adm-limit">
        <div class="adm-meter"><p><b>Humanizer · per day</b><span class="muted">${admFmt(used)} used today</span></p>
          <div class="credit-bar adm-bar-ok" aria-hidden="true"><span style="width:${v.humLimit ? Math.max(0, Math.round((v.humLimit - used) / v.humLimit * 100)) : 0}%"></span></div>
          <p class="small muted">Shared by all users · resets at 00:00</p></div>
        <div class="adm-stepper"><button class="btn adm-step" data-act="adm-hum" data-v="-10" aria-label="Decrease daily limit">−</button>
          <output class="adm-stat" aria-live="polite">${v.humLimit}</output><button class="btn adm-step" data-act="adm-hum" data-v="10" aria-label="Increase daily limit">+</button></div>
      </div>
      <hr>
      <div class="adm-limit">
        <div><p class="adm-row"><b>Turnitin pool</b><span class="lvl ${poolState[1] === 'red' ? 'lvl-high' : poolState[1] === 'amber' ? 'lvl-warn' : 'lvl-low'}">${poolState[0]}</span></p>
          <p class="adm-stat">${admFmt(pool)} <span class="small muted">checks left</span></p>
          <p class="small muted">Shared by all users · doesn’t reset</p></div>
        <div class="adm-pool"><div class="adm-chips">${[100, 500, 1000].map(n => `<button class="adm-chip adm-amt" aria-pressed="${n === s.topup}" data-act="adm-topup" data-v="${n}">+${n}</button>`).join('')}</div>
          <button class="btn btn-primary" data-act="adm-addpool">Add ${s.topup} checks</button></div>
      </div>
    </section>

    <section class="card adm-card" id="adm-services" aria-labelledby="adm-svc-h">
      <div class="adm-card-head"><div><h2 id="adm-svc-h">AI services</h2><p class="small muted">Configuration check. Checks don’t spend credits.</p></div>
        <button class="btn btn-sm" data-act="adm-sess" ${sw === 'checking' ? 'disabled' : ''}>${sw && sw !== 'checking' ? 'Check again' : 'Check Humanizer session'}</button></div>
      <ul class="adm-svc">
        <li><span class="adm-dot ${sess[2]}" aria-hidden="true"></span><span><span>Humanizer session (StealthWriter)</span><span class="small muted">${esc(sess[0])}</span></span><span class="adm-svc-st ${sess[2]}">${sess[1]}</span></li>
        ${!services ? `<li><span class="adm-dot" aria-hidden="true"></span><span><span>${s.err.pre ? esc(s.err.pre) : 'Checking services…'}</span></span>${s.err.pre ? '<button class="link-btn" data-act="adm-retry" data-v="pre">Try again</button>' : ''}</li>`
          : services.map(c => {
            const st = c.ok ? ['ok', 'OK'] : c.required ? ['red', 'Not set up'] : ['amber', 'Off'];
            return `<li><span class="adm-dot ${st[0]}" aria-hidden="true"></span><span><span>${esc(c.label)}</span><span class="small muted">${esc(c.detail || '')}</span></span><span class="adm-svc-st ${st[0]}">${st[1]}</span></li>`;
          }).join('')}
      </ul>
    </section>

    <section class="card adm-card" id="adm-data" aria-labelledby="adm-data-h">
      <div class="adm-card-head"><div><h2 id="adm-data-h">Training data</h2><p class="small muted">Collected for future fine-tuning. Cleaned on export.</p></div>
        <a class="link-btn" href="/admin/dataset-stats" target="_blank" rel="noopener">Full stats &amp; export</a></div>
      ${D ? `<div class="adm-stats adm-stats-2">
        <div><p class="small muted">Humanizer samples</p><p class="adm-stat">${admFmt(D.total)}</p><p class="small muted">${admFmt(D.standalone)} standalone · ${admFmt(D.assignment)} assignments${D.workspace_partial ? ` · ${admFmt(D.workspace_partial)} editor` : ''}</p></div>
        <div><p class="small muted">AI detection logs</p><p class="adm-stat">${admFmt(D.detector_total)}</p><p class="small muted">${admFmt(D.auto_report_over_20)} auto (&gt;20% + highlights) · ${admFmt(D.manual_highlights)} manual</p></div>
      </div>` : `<p class="small muted">${s.err.data ? esc(s.err.data) : 'Loading…'}</p>`}
    </section>

    ${changes.length ? `<div class="adm-savebar"><span>Unsaved: ${changes.join(', ')}</span>
      <button class="btn" data-act="adm-discard" ${s.saving ? 'disabled' : ''}>Discard</button><button class="btn btn-primary" data-act="adm-save" ${s.saving ? 'disabled' : ''}>${s.saving ? 'Saving…' : 'Save changes'}</button></div>` : ''}
    ${s.savedMsg && !changes.length ? `<div class="adm-savebar adm-saved" role="status">Saved. Live for all users now — recorded in Activity.</div>` : ''}
  </div>`;
}

function renderAdminDenied() {
  return `<div class="page">${pageHead(ITEMS.admin)}<section class="card help-contact"><div class="empty"><strong>Admins only</strong>Sign in with an admin account to open the admin panel.<br><br><a class="btn btn-primary" href="#/home">Back to app</a></div></section></div>`;
}
const adminPage = (fn) => () => canAdmin() ? fn() : renderAdminDenied();

// Re-render only the admin page, keep the scroll and focus
function rerenderAdmin(focusSel) {
  const y = window.scrollY, active = document.activeElement;
  const inMain = active && active !== document.body && $('#main').contains(active);
  let sel = focusSel, caret = null;
  if (!sel && inMain) {
    if (active.id) sel = '#' + active.id;
    else if (active.dataset.act) sel = `[data-act="${active.dataset.act}"]` + ['v', 'id', 'k'].map(k => active.dataset[k] !== undefined ? `[data-${k}="${active.dataset[k]}"]` : '').join('');
    if (active.matches('input[type="search"]')) caret = active.selectionStart;
  }
  $('#main').innerHTML = PAGES[ALL_ITEMS.find(i => i.route === currentRoute()).id]();
  bindAdmin();
  renderSidebar();
  window.scrollTo(0, y);
  const el = sel ? $(sel) : null;
  if (el) {
    el.focus({ preventScroll: true });
    if (caret !== null) el.setSelectionRange(caret, caret);
  }
}

let admSearchTimer = null;
function bindAdmin() {
  const s = adminState();
  const search = (id, key, field, reset) => $(id)?.addEventListener('input', (e) => {
    s[field] = e.target.value;
    reset();
    clearTimeout(admSearchTimer);
    admSearchTimer = setTimeout(() => admLoad(key), 250);
  });
  search('#adm-u-q', 'users', 'uQuery', () => { s.uOffset = 0; });
  search('#adm-a-q', 'feed', 'aQuery', () => { s.openId = null; });
  $('#adm-reason')?.addEventListener('change', (e) => { s.lastReason = e.target.value; });
  $('#adm-auto-time')?.addEventListener('change', (e) => { (s.draft = s.draft || {}).autoTime = e.target.value || '20:00'; s.savedMsg = false; rerenderAdmin(); });
  $('#adm-auto-min')?.addEventListener('change', (e) => { (s.draft = s.draft || {}).autoMin = Math.max(0, parseInt(e.target.value, 10) || 0); s.savedMsg = false; rerenderAdmin(); });
}

// Run a change on the server, then refresh what it affects
async function admRun(work, { ok, reload = ['users', 'detail', 'ov'], focus } = {}) {
  const s = adminState();
  s.busy = true; rerenderAdmin();
  try {
    const res = await work();
    if (ok) toast(typeof ok === 'function' ? ok(res) : ok);
    reload.forEach(k => { if (k !== 'detail' || s.selId) admLoad(k); });
    return res;
  } catch (e) {
    toast(e.message || 'Something went wrong. Try again.');
    return null;
  } finally {
    s.busy = false;
    if (isAdminRoute()) rerenderAdmin(focus);
  }
}

async function admApplyCredits(delta, reason, isUndo) {
  const s = adminState(), id = s.selId;
  const res = await admRun(() => API.admin.credits(id, delta, reason), { reload: ['users', 'detail'], focus: '[data-act="adm-apply"]' });
  if (!res) return;
  const n = Math.abs(res.delta);
  if (isUndo) { s.done = null; s.undo = null; toast(`Undone · ${res.delta > 0 ? 'returned' : 'removed'} ${admFmt(n)} credits`); }
  else { s.done = `${res.delta > 0 ? 'Added' : 'Removed'} ${admFmt(n)} credits · logged`; s.undo = { delta: -res.delta }; }
  if (s.detail && s.detail.user.id === id) s.detail.user.credits = res.balance;
  if (CONFIG.user.id === '#' + id) loadCredits();
  if (isAdminRoute()) rerenderAdmin(isUndo ? '[data-act="adm-apply"]' : '[data-act="adm-undo"]');
}

async function admOlder() {
  const s = adminState(), F = s.feed;
  if (!F || F.nextOffset == null || s.older) return;
  s.older = true; rerenderAdmin();
  try {
    const more = await API.admin.activity({ cat: s.aCat, q: s.aQuery.trim(), hide_bots: s.hideBots ? 1 : 0, hide_staff: s.hideStaff ? 1 : 0, offset: F.nextOffset });
    if (s.feed === F) Object.assign(F, { events: F.events.concat(more.events), nextOffset: more.nextOffset, hiddenBots: F.hiddenBots + more.hiddenBots });
  } catch (e) { toast(e.message || 'Could not load older activity.'); }
  s.older = false;
  if (isAdminRoute()) rerenderAdmin('[data-act="adm-older"]');
}

async function admSave() {
  const s = adminState(), sv = admSaved(), v = { ...sv, ...(s.draft || {}) };
  const patch = {};
  if (v.mode !== sv.mode) { patch.is_humanizer_discount_active = v.mode === 'manual'; patch.auto_discount_enabled = v.mode === 'auto'; }
  if (v.percent !== sv.percent) patch.humanizer_discount_percent = v.percent;
  if (v.autoTime !== sv.autoTime) patch.auto_discount_time = v.autoTime;
  if (v.autoMin !== sv.autoMin) patch.auto_discount_min_remaining = v.autoMin;
  if (v.humLimit !== sv.humLimit) patch.humanizer_daily_limit = v.humLimit;
  s.saving = true; rerenderAdmin();
  try {
    if (v.poolAdd) {
      // The pool shrinks with every check, so add on top of the current value, not the one on screen
      const fresh = await API.admin.dailyStats();
      patch.turnitin_global_balance = Number((fresh.settings || {}).turnitin_global_balance || 0) + v.poolAdd;
    }
    const res = await API.admin.siteSettings(patch);
    Object.assign(s.ov, { settings: res.settings, today: res.today || s.ov.today, discount: res.discount || s.ov.discount });
    s.draft = null; s.savedMsg = true;
    admLoad('ov');
  } catch (e) {
    toast(e.message || 'Could not save. Try again.');
  }
  s.saving = false;
  if (isAdminRoute()) rerenderAdmin();
}

function adminAction(act, el) {
  const s = adminState(), v = el.dataset.v, keep = (sel) => rerenderAdmin(sel);
  const draft = () => (s.draft = s.draft || {});
  const u = admSelUser();
  switch (act) {
    case 'adm-period': s.period = v; keep(`[data-act="adm-period"][data-v="${v}"]`); break;
    case 'adm-excl': s.excl = !s.excl; keep('[data-act="adm-excl"]'); break;
    case 'adm-refresh': admLoad(v || 'ov'); if (!v) admLoad('pre'); break;
    case 'adm-retry': s.err[v] = null; admLoad(v); keep(); break;
    case 'adm-go':
      if (el.dataset.cat) s.aCat = el.dataset.cat;
      if (el.dataset.q) { s.aQuery = el.dataset.q; s.aCat = 'all'; }
      if (el.dataset.cat || el.dataset.q) { s.feed = null; s.openId = null; admLoad('feed'); }
      if (el.dataset.filter) { s.uFilter = el.dataset.filter; s.uOffset = 0; s.users = null; admLoad('users'); }
      go(el.dataset.to);
      if (el.dataset.anchor) setTimeout(() => $('#' + el.dataset.anchor)?.scrollIntoView({ behavior: 'smooth' }), 80);
      break;
    case 'adm-ufilter': s.uFilter = v; s.uOffset = 0; admLoad('users'); keep(`[data-act="adm-ufilter"][data-v="${v}"]`); break;
    case 'adm-prev': s.uOffset = Math.max(0, s.uOffset - ADM_PAGE); admLoad('users'); break;
    case 'adm-next': s.uOffset += ADM_PAGE; admLoad('users'); break;
    case 'adm-open':
      s.selId = +el.dataset.id; s.uTab = 'overview'; s.done = null; s.undo = null; s.detail = null; s.err.detail = null;
      admLoad('detail'); keep('[data-act="adm-close"]'); break;
    case 'adm-close': { const id = s.selId; s.selId = null; s.detail = null; keep(`[data-act="adm-open"][data-id="${id}"]`); break; }
    case 'adm-utab': s.uTab = v; keep(`[data-act="adm-utab"][data-v="${v}"]`); break;
    case 'adm-mode': s.mode = v; keep(`[data-act="adm-mode"][data-v="${v}"]`); break;
    case 'adm-amount': s.amount = +v; keep(`[data-act="adm-amount"][data-v="${v}"]`); break;
    case 'adm-apply': {
      if (!u) break;
      const delta = s.mode === 'add' ? s.amount : -Math.min(s.amount, u.credits);
      if (delta) admApplyCredits(delta, $('#adm-reason')?.value || s.lastReason);
      break;
    }
    case 'adm-undo': if (s.undo) admApplyCredits(s.undo.delta, 'Undo', true); break;
    case 'adm-block':
      if (u) admRun(() => API.admin.block(u.id, true, el.dataset.bonus === '1'),
        { ok: (r) => `#${u.id} blocked${r.bonusRemoved ? ` · −${r.bonusRemoved} bonus credits` : ''}`, focus: '[data-act="adm-unblock"]' });
      break;
    case 'adm-unblock': if (u) admRun(() => API.admin.block(u.id, false), { ok: `#${u.id} unblocked`, focus: '[data-act="adm-block"]' }); break;
    case 'adm-clear': if (u) admRun(() => API.admin.clear(u.id, true), { ok: 'Flag removed', focus: '[data-act="adm-close"]' }); break;
    case 'adm-flag': if (u) admRun(() => API.admin.flag(u.id, v || null), { ok: v ? `Marked as ${v}` : 'Unmarked', focus: '[data-act="adm-close"]' }); break;
    case 'adm-block-all': {
      const ids = (s.users ? s.users.users : []).filter(x => x.flag === 'susp').map(x => x.id);
      if (!ids.length) break;
      askConfirm({
        title: `Block ${ids.length} account${ids.length > 1 ? 's' : ''}?`, okLabel: 'Block all', opener: el,
        text: 'They won’t be able to sign in, and their unspent welcome bonus is removed. You can unblock each one later.',
        onOk: () => { admRun(() => API.admin.blockMany(ids), { ok: (r) => `${r.blocked.length} account${r.blocked.length === 1 ? '' : 's'} blocked` }); return null; },
      });
      break;
    }
    case 'adm-role':
      if (!u) break;
      askConfirm({
        title: u.isAdmin ? `Remove admin access from #${u.id}?` : `Make #${u.id} an admin?`, opener: el,
        okLabel: u.isAdmin ? 'Remove access' : 'Make admin',
        text: u.isAdmin ? `${u.email} will lose access to the admin panel.`
          : `${u.email} will get full control of credits, prices and users, including other admins.`,
        onOk: () => { admRun(() => API.admin.setAdmin(u.id, !u.isAdmin), { ok: u.isAdmin ? 'Admin access removed' : 'Admin access granted' }); return null; },
      });
      break;
    case 'adm-delete':
      if (!u) break;
      askConfirm({
        title: `Delete #${u.id}?`, opener: el, okLabel: 'Delete account',
        text: `${u.email} and their balance are deleted for good. Their history stays in Activity. This can’t be undone.`,
        onOk: () => {
          admRun(() => API.admin.deleteUser(u.id), { ok: `#${u.id} deleted`, reload: ['users', 'ov'] })
            .then(r => { if (r) { s.selId = null; s.detail = null; if (isAdminRoute()) rerenderAdmin(); } });
          return null;
        },
      });
      break;
    case 'adm-acat': s.aCat = v; s.openId = null; admLoad('feed'); keep(`[data-act="adm-acat"][data-v="${v}"]`); break;
    case 'adm-bots': s.hideBots = !s.hideBots; admLoad('feed'); keep('[data-act="adm-bots"]'); break;
    case 'adm-staff': s.hideStaff = !s.hideStaff; admLoad('feed'); keep('[data-act="adm-staff"]'); break;
    case 'adm-ev': { const id = +el.dataset.id; s.openId = s.openId === id ? null : id; keep(`[data-act="adm-ev"][data-id="${id}"]`); break; }
    case 'adm-older': admOlder(); break;
    case 'adm-anchor': $('#' + v)?.scrollIntoView({ behavior: 'smooth' }); break;
    case 'adm-set': draft()[el.dataset.k] = el.dataset.k === 'percent' ? +v : v; s.savedMsg = false; keep(`[data-act="adm-set"][data-k="${el.dataset.k}"][data-v="${v}"]`); break;
    case 'adm-hum': { const cur = s.draft?.humLimit ?? admSaved().humLimit; draft().humLimit = Math.max(10, cur + +v); s.savedMsg = false; keep(`[data-act="adm-hum"][data-v="${v}"]`); break; }
    case 'adm-topup': s.topup = +v; keep(`[data-act="adm-topup"][data-v="${v}"]`); break;
    case 'adm-addpool': draft().poolAdd = (s.draft.poolAdd || 0) + s.topup; s.savedMsg = false; keep('[data-act="adm-addpool"]'); break;
    case 'adm-sess':
      s.sess = 'checking'; keep('[data-act="adm-sess"]');
      API.admin.preflight(true).then(res => {
        const c = (res.checks || []).find(x => x.id === 'stealthwriter');
        s.sess = c ? { ok: !!c.ok, detail: c.ok ? 'Logged in' : c.detail } : { ok: false, detail: 'No answer from the browser engine' };
      }).catch(e => { s.sess = { ok: false, detail: e.message || 'Check failed' }; })
        .finally(() => { if (currentRoute() === 'admin-settings') keep('[data-act="adm-sess"]'); });
      break;
    case 'adm-discard': s.draft = null; keep(); break;
    case 'adm-save': admSave(); break;
  }
}

const PAGES = {
  home: renderHome,
  humanizer: () => renderTextTool('humanizer'),
  turnitin: renderScan,
  veil: renderVeil,
  workspace: renderEditor,
  presentation: renderSlides,
  format: () => { fmtState().mode = workDocMode(fmtState().mode); return renderFormat(); },
  check: () => { reviewState().docMode = workDocMode(reviewState().docMode); return renderReview(); },
  assignment: renderAssignment,
  help: renderHelp,
  pricing: renderPricing,
  earn: renderEarn,
  account: renderAccountInfo,
  settings: renderAccount,
  billing: renderBilling,
  admin: adminPage(renderAdminOverview),
  'admin-users': adminPage(renderAdminUsers),
  'admin-activity': adminPage(renderAdminActivity),
  'admin-settings': adminPage(renderAdminSettings),
};
CONFIG.legal.forEach(d => { PAGES[d.id] = () => renderLegal(d.id); });

function render() {
  hideTip();
  if (tour.name) { tour.name = null; $('#tour').hidden = true; }
  const route = currentRoute();
  const main = $('#main');
  const isPublic = PUBLIC_ROUTES.includes(route);
  $('#app').classList.toggle('is-public', isPublic);
  syncProto();
  if (isPublic) {
    document.body.classList.remove('on-editor', 'on-format', 'on-assign');
    main.innerHTML = renderLanding();
    document.title = CONFIG.brand;
    window.scrollTo(0, 0);
    bindLanding();
    return;
  }
  const item = ALL_ITEMS.find(i => i.route === route);
  document.body.classList.toggle('on-editor', item.id === 'workspace');
  document.body.classList.toggle('on-format', item.id === 'format');
  document.body.classList.toggle('on-assign', item.id === 'assignment');
  if (formatState) formatState.previewOpen = false;
  hideSelPop(); edCloseMenu();
  document.body.classList.toggle('on-admin', isAdminRoute(route));
  if (isCollapsed() !== state.lastCollapsed) { renderSidebar(); applyLayout(); }
  else if (isAdminRoute(route) !== !!state.admMode) renderSidebar();
  state.admMode = isAdminRoute(route);
  main.innerHTML = (PAGES[item.id] || (() => renderStub(item)))();
  document.title = `${item.label} — ${CONFIG.brand}`;
  markActive();
  bindPage(item.id);
  const tourName = Object.keys(CONFIG.tours).find(k => CONFIG.tours[k].route === item.route);
  if (tourName && (state.pendingTour === tourName || !store.get('tour-' + tourName + '-seen', false))) {
    state.pendingTour = null;
    setTimeout(() => { if (currentRoute() === CONFIG.tours[tourName].route) startTour(tourName); }, 50);
  }
  if (state.drawerOpen) { state.drawerOpen = false; applyLayout(); main.focus(); }
  window.scrollTo(0, 0);
}

function go(route) { location.hash = '#/' + route; }

/* =========================================================
   Pages
   ========================================================= */
// Page title as in the Humanizer mockup: title + chips, description, optional action on the right.
// `title` in CONFIG overrides the menu label on the page itself (e.g. "AI Detector — Turnitin").
function pageHead(item, extra = '', action = '') {
  return `<header class="tool-head">
    <div>
      <h1>${esc(item.title || item.label)} ${badgeHtml(item)} ${extra}</h1>
      <p class="lead">${esc(item.description)}</p>
    </div>
    ${action}
  </header>`;
}

/* ---------- Home ---------- */
function creditAmountHtml(c) {
  if (c.amount > 0) return `<span class="free">+${c.amount}</span>`;
  if (c.amount === 0) return '<span class="free">Free</span>';
  if (c.amount < 0) return '−' + Math.abs(c.amount);
  return '−' + esc(CONFIG.pricePlaceholder.replace(/\s*credits?$/, ''));
}

/* ---------- Home ---------- */
const H = () => CONFIG.homePage;
const estCredits = (tool) => H().estimates[tool];
const estLabel = (tool) => (estCredits(tool) != null ? `~${estCredits(tool)} credits` : CONFIG.pricePlaceholder);

function renderHome() {
  const signed = state.signedIn;
  return `<div class="page home">
    ${introVideoHtml()}
    ${quickStartHtml()}
    <div class="home-cols">
      ${signed ? homeCreditsHtml() : promoHtml()}
      ${homeHistoryHtml()}
    </div>
    ${tasksHtml()}
  </div>`;
}

// Video overview for a new account (nothing made yet); hidden for good once closed
function introVideoHtml() {
  if (!state.signedIn || state.docs.length || store.get(introKey(), false)) return '';
  const V = H().introVideo;
  return `<section class="card intro-video" aria-labelledby="intro-h">
    <button class="intro-thumb" type="button" data-act="intro-play" aria-label="${esc(V.cta)}">
      <span class="tut-play" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z"/></svg></span>
      <span class="intro-len">2:00</span>
    </button>
    <div class="intro-body">
      <h2 id="intro-h">${esc(V.title)}</h2>
      <p class="muted">${esc(V.text)}</p>
      <div class="intro-actions">
        <button class="btn btn-sm btn-primary" type="button" data-act="intro-play">${icon('video')} ${esc(V.cta)}</button>
        <button class="btn btn-sm btn-ghost" type="button" data-act="open-tutorials">${esc(V.more)}</button>
      </div>
    </div>
    <button class="icon-btn intro-close" type="button" data-act="intro-hide" aria-label="Hide the video overview">${icon('close')}</button>
  </section>`;
}

// One column on Home: big title (+ optional action) above a white card
function homeColHtml(id, title, body, action = '', boxId = '') {
  return `<section class="home-col" aria-labelledby="${id}">
    <div class="home-col-head"><h2 id="${id}" class="home-h" tabindex="-1">${title}</h2>${action}</div>
    <div class="card home-box" ${boxId ? `id="${boxId}"` : ''}>${body}</div>
  </section>`;
}

function promoHtml() {
  return homeColHtml('promo-h', esc(H().titles.guestCredits), `<div class="box-head">
      <div><p class="box-title">Sign up and get ${CONFIG.signupCredits} credits</p>
        <p class="box-sub">${freeNoteHtml()}. Humanizer: <span class="free">${esc(ITEMS.humanizer.guestPrice)}</span> without an account.</p></div>
      <button class="btn btn-sm btn-primary" data-act="signup">Sign up</button></div>`);
}

/* Start here: one field, then Humanize or Check for AI (main) */
function quickStartHtml() {
  const has = !!(workDoc.file || workDoc.text.trim());
  const humanizeCost = !state.signedIn && state.guestRunsUsed < 1 ? ITEMS.humanizer.guestPrice : estLabel('humanizer');
  return `<section class="qs" id="qs" aria-labelledby="qs-h">
    <h1 id="qs-h" class="qs-title" tabindex="-1">${esc(H().startTitle)}</h1>
    <div class="qs-field">
      <button class="qs-add" type="button" data-act="qs-upload" aria-label="Upload a file"
        data-tip-title="Upload a file" data-tip-desc=".docx, .pdf or .txt" data-tip-pos="bottom">${icon('plus')}</button>
      ${workDoc.file
        ? `<span class="file-chip">${icon('file')}<span class="file-name">${esc(workDoc.file.name)}</span><span class="muted small">${fmtSize(workDoc.file.size)}</span>
             <button class="chip-x" data-act="qs-remove-file" aria-label="Remove ${esc(workDoc.file.name)}">${icon('close')}</button></span>`
        : `<label class="visually-hidden" for="qs-text">Your text</label>
           <textarea id="qs-text" class="qs-input" rows="1" placeholder="${esc(H().startPlaceholder)}">${esc(workDoc.text)}</textarea>`}
      <input type="file" id="qs-file" accept=".docx,.pdf,.txt" hidden>
    </div>
    <div class="qs-actions">
      <button class="btn" data-act="qs-humanize" ${has ? '' : 'disabled'} data-tip-title="Humanize" data-tip-desc="${esc(humanizeCost)}" data-tip-pos="bottom">${icon('sparkles')} Humanize</button>
      <button class="btn btn-primary" data-act="qs-check" ${has ? '' : 'disabled'} data-tip-title="Check for AI" data-tip-desc="${esc(estLabel('turnitin'))}" data-tip-pos="bottom">${icon('scan')} Check for AI</button>
    </div>
  </section>`;
}

/* Continue: the latest documents with their next step */
function nextStep(d) {
  switch (d.tool) {
    case 'turnitin': return d.ai != null && d.ai <= CONFIG.scan.highlightsMinAi
      ? { status: `AI ${d.ai}%`, label: 'Format', go: 'format' }
      : { status: d.ai != null ? `AI ${d.ai}%` : 'AI checked', label: 'Humanize', go: 'humanize' };
    case 'humanizer': return { status: 'Humanized', label: 'Recheck', go: 'recheck' };
    case 'format': return { status: 'Formatted', label: 'Review', go: 'check' };
    case 'check': return { status: 'Reviewed', label: 'Fix formatting', go: 'format' };
    case 'assignment': return { status: 'Draft', label: 'Open chat', go: 'assignment' };
    case 'presentation': return { status: 'Slides ready', label: 'Open slides', go: 'presentation' };
    default: return null;
  }
}

/* Credit history: balance, what it is enough for, top-up, latest operations */
function homeCreditsHtml() {
  const b = state.balance, low = b <= H().lowBalance;
  const checks = estCredits('turnitin') ? Math.floor(b / estCredits('turnitin')) : null;
  const runs = estCredits('humanizer') ? Math.floor(b / estCredits('humanizer')) : null;
  const list = state.creditsAll ? state.credits : state.credits.slice(0, H().creditHistoryPreview);
  const more = state.credits.length - H().creditHistoryPreview;
  return homeColHtml('hc-h', esc(H().titles.credits), `
    <div class="box-head">
      <div><p class="box-title">${b} credits left</p>
        ${checks != null ? `<p class="box-sub">Enough for ~${checks} AI checks or ~${runs} humanizer runs.</p>` : ''}</div>
    </div>
    ${low ? '<div class="hc-low" role="status"><b>Running low.</b> Top up to keep checking and humanizing.</div>' : ''}
    ${state.credits.length ? `<ul class="box-list" id="hc-list">${list.map(c => `<li class="box-row">
        <span class="doc-icon">${icon(c.tool ? ITEMS[c.tool].icon : 'coins')}</span>
        <span class="box-row-main"><span class="box-row-title">${esc(c.label)}</span><span class="box-row-sub">${fmtDate(c.date)}</span></span>
        <span class="row-amount">${creditAmountHtml(c)}</span></li>`).join('')}</ul>
      ${more > 0 ? `<div class="box-foot"><button class="btn btn-sm btn-ghost" data-act="credits-more" aria-expanded="${!!state.creditsAll}" aria-controls="hc-list">
        ${state.creditsAll ? 'Show less' : `Show more (${more})`}</button></div>` : ''}`
      : '<div class="empty">No credit activity yet</div>'}`);
}

/* History: latest documents with their next step; "Show more" adds filter and delete */
function homeHistoryHtml() {
  return homeColHtml('hist-h', esc(H().titles.history), historyHtml(), '', 'home-history');
}

function historyHtml() {
  if (!state.docs.length) {
    return `<div class="empty"><strong>No documents yet</strong>Your work from every tool will appear here.</div>`;
  }
  const all = state.historyAll;
  const tools = [...new Set(state.docs.map(d => d.tool))];
  const filtered = state.docs.filter(d => state.docFilter === 'all' || d.tool === state.docFilter);
  const list = all ? filtered : filtered.slice(0, H().recentCount);
  const more = filtered.length - H().recentCount;
  return `<div class="box-head">
      <div><p class="box-title">${state.docs.length} document${state.docs.length > 1 ? 's' : ''}</p><p class="box-sub">${esc(H().historySub)}</p></div>
      <label class="visually-hidden" for="doc-filter">Filter by tool</label>
      <select class="pill-select" id="doc-filter">
        <option value="all">All tools</option>
        ${tools.map(id => `<option value="${id}" ${state.docFilter === id ? 'selected' : ''}>${esc(ITEMS[id].label)}</option>`).join('')}
      </select>
    </div>
    ${list.length ? `<ul class="box-list" id="hist-list">${list.map(d => {
      const t = ITEMS[d.tool], n = nextStep(d);
      return `<li class="box-row">
        <span class="doc-icon">${icon(t.icon)}</span>
        <span class="box-row-main"><a class="box-row-title doc-title" href="#/${t.route}">${esc(d.title)}</a>
          <span class="box-row-sub">${esc(t.label)} · ${fmtDate(d.date)}</span></span>
        ${all ? `<button class="icon-btn" data-act="delete-doc" data-id="${d.id}" aria-label="Delete “${esc(d.title)}”">${icon('trash')}</button>`
          : n ? `<button class="btn btn-sm" data-act="continue" data-id="${d.id}" aria-label="${esc(n.label)}: ${esc(d.title)}">${esc(n.label)}</button>` : ''}
      </li>`;
    }).join('')}</ul>`
      : `<div class="empty"><strong>No documents for this tool</strong><button class="btn btn-sm" data-act="clear-filter">Show all</button></div>`}
    ${more > 0 ? `<div class="box-foot"><button class="btn btn-sm btn-ghost" data-act="${all ? 'history-less' : 'history-all'}" aria-expanded="${all}" aria-controls="hist-list">
      ${all ? 'Show less' : `Show more (${more})`}</button></div>` : ''}`;
}

/* What else do you need: the other tools as small tiles */
// Solar icons (Bold Duotone, CC BY 4.0, 480 Design) for the home tool tiles, keyed by tool id
const SOLAR = {
  assignment: '<path fill-rule="evenodd" d="M20.0821 3.01774C21.1538 2.98054 22.0001 3.86139 22.0001 4.93375V16.1437C22.0001 17.2546 21.0941 18.1533 19.9854 18.2228C19.016 18.2834 17.8768 18.4026 17.0001 18.6339C15.9186 18.9193 15.0102 19.7011 13.627 20.0695C13.001 20.2362 12.3029 20.326 12.0001 20.3927V5.17399C12.3208 5.09543 13.3825 4.97156 13.6739 4.80289C13.8581 4.69626 14.0513 4.5874 14.2501 4.47965V7.53727C14.2499 7.64849 14.2493 7.8074 14.2706 7.94352C14.2966 8.10994 14.3826 8.43087 14.7149 8.62614C15.0353 8.81425 15.3492 8.7447 15.4981 8.6984C15.6279 8.65804 15.7699 8.58977 15.876 8.53922L17.0001 8.00602L18.1241 8.53922C18.2302 8.58977 18.3723 8.65804 18.502 8.6984C18.651 8.7447 18.9649 8.81425 19.2852 8.62614C19.6175 8.43088 19.7035 8.10994 19.7296 7.94352C19.7508 7.80741 19.7502 7.64849 19.7501 7.53727V3.03141C19.8629 3.02611 19.9739 3.02151 20.0821 3.01774ZM19.7276 12.8185C19.6272 12.4167 19.2202 12.1723 18.8184 12.2726L14.8184 13.2726C14.4167 13.3731 14.1722 13.78 14.2725 14.1818C14.373 14.5836 14.7799 14.828 15.1817 14.7277L19.1817 13.7277C19.5835 13.6273 19.8279 13.2203 19.7276 12.8185Z" clip-rule="evenodd"/><path d="M4.27253 12.8185C4.37296 12.4168 4.78001 12.1724 5.18171 12.2726L9.18171 13.2726C9.58344 13.3731 9.82784 13.7801 9.72761 14.1818C9.62715 14.5836 9.22027 14.8281 8.81843 14.7277L4.81843 13.7277C4.41662 13.6272 4.17214 13.2203 4.27253 12.8185Z"/><path d="M4.27253 8.81852C4.37296 8.41682 4.78001 8.17245 5.18171 8.27262L9.18171 9.27262C9.58344 9.37305 9.82784 9.78007 9.72761 10.1818C9.62715 10.5836 9.22027 10.8281 8.81843 10.7277L4.81843 9.7277C4.41662 9.62725 4.17214 9.22033 4.27253 8.81852Z"/><path d="M18.2501 6.93864L17.501 6.58317L17.4923 6.57828C17.4531 6.55827 17.3129 6.48706 17.1378 6.45914C17.0938 6.45214 17.0475 6.44743 17.0001 6.44743C16.7637 6.44743 16.5569 6.55323 16.5079 6.57828L16.4991 6.58317L15.7501 6.93864V3.757C16.0063 3.65201 16.2585 3.55977 16.5001 3.48746C17.0206 3.33165 17.6301 3.22482 18.2501 3.15153V6.93864Z"/><path d="M12 5.21395C11.6658 5.15047 10.9426 5.05264 10.2823 4.87544C8.9381 4.51475 8.04921 3.76429 7 3.48742C6.11349 3.25349 4.95877 3.13488 3.9824 3.07487C2.8863 3.0075 2 3.89961 2 4.99778V16.1436C2 17.2545 2.90605 18.1534 4.01486 18.2228C4.98428 18.2834 6.12329 18.402 7 18.6333C7.48596 18.7616 8.21615 19.0645 8.87295 19.3592C9.87752 19.81 10.9247 20.1556 12 20.3926V5.21395Z" opacity=".5"/>',
  workspace: '<path d="M1 12C1 6.81455 1 4.22183 2.61091 2.61091C4.22183 1 6.81455 1 12 1C17.1854 1 19.7782 1 21.3891 2.61091C23 4.22183 23 6.81455 23 12C23 17.1854 23 19.7782 21.3891 21.3891C19.7782 23 17.1854 23 12 23C6.81455 23 4.22183 23 2.61091 21.3891C1 19.7782 1 17.1854 1 12Z" opacity=".5"/><path d="M13.9261 14.3018C14.1711 14.1107 14.3933 13.8885 14.8377 13.4441L20.378 7.90374C20.512 7.7698 20.4507 7.53909 20.2717 7.477C19.6178 7.25011 18.767 6.82414 17.9713 6.02835C17.1755 5.23257 16.7495 4.38186 16.5226 3.72788C16.4605 3.54892 16.2298 3.48761 16.0959 3.62156L10.5555 9.16192C10.1111 9.60634 9.88888 9.82854 9.69778 10.0736C9.47235 10.3626 9.27908 10.6753 9.12139 11.0062C8.98771 11.2867 8.88834 11.5848 8.68959 12.181L8.43278 12.9515L8.02443 14.1765L7.64153 15.3252C7.54373 15.6186 7.6201 15.9421 7.8388 16.1608C8.0575 16.3795 8.38099 16.4559 8.67441 16.3581L9.82308 15.9752L11.0481 15.5668L11.8186 15.31L11.8186 15.31C12.4148 15.1113 12.7129 15.0119 12.9934 14.8782C13.3243 14.7205 13.637 14.5273 13.9261 14.3018Z"/><path d="M22.1127 6.16905C23.2952 4.98656 23.2952 3.06936 22.1127 1.88687C20.9302 0.704377 19.013 0.704377 17.8306 1.88687L17.6524 2.06499C17.4806 2.23687 17.4027 2.47695 17.4456 2.7162C17.4726 2.8667 17.5227 3.08674 17.6138 3.3493C17.796 3.87439 18.14 4.56368 18.788 5.21165C19.4359 5.85961 20.1252 6.20364 20.6503 6.38581C20.9129 6.4769 21.1329 6.52697 21.2834 6.55399C21.5227 6.59693 21.7627 6.51905 21.9346 6.34717L22.1127 6.16905Z"/>',
  presentation: '<path d="M4 10.5V2.75H20V10.5C20 13.5641 20 15.0962 18.9958 16.0481C17.9916 17 16.3753 17 13.1429 17H12.75H11.25H10.8571C7.62465 17 6.00841 17 5.00421 16.0481C4 15.0962 4 13.5641 4 10.5Z" opacity=".5"/><path d="M12.75 17V20.5361L14.3359 21.3291C14.7061 21.5144 14.8558 21.9646 14.6709 22.335C14.4857 22.7054 14.0355 22.8559 13.665 22.6709L12 21.8389L10.3359 22.6709C9.96545 22.8561 9.51434 22.7054 9.3291 22.335C9.14421 21.9646 9.29471 21.5143 9.66504 21.3291L11.25 20.5361V17H12.75Z"/><path d="M14.4697 7.96973C14.7626 7.67683 15.2374 7.67683 15.5303 7.96973C15.8232 8.26262 15.8232 8.73738 15.5303 9.03027L14.2129 10.3477C14.0679 10.4927 13.9109 10.6491 13.7607 10.7637C13.5848 10.8979 13.3335 11.043 13 11.043C12.6668 11.043 12.4152 10.8988 12.2393 10.7646C12.0891 10.6501 11.9321 10.4927 11.7871 10.3477L11.1768 9.7373C11.1068 9.66733 11.0499 9.61078 11 9.5625C10.9501 9.61078 10.8932 9.66733 10.8232 9.7373L9.53027 11.0303C9.23738 11.3232 8.76262 11.3232 8.46973 11.0303C8.17683 10.7374 8.17683 10.2626 8.46973 9.96973L9.78711 8.65234C9.93205 8.50729 10.0891 8.35088 10.2393 8.23633C10.4152 8.1021 10.6665 7.95703 11 7.95703C11.3335 7.95703 11.5848 8.1021 11.7607 8.23633C11.9109 8.35088 12.0679 8.50729 12.2129 8.65234L12.8232 9.2627C12.8932 9.33267 12.9501 9.38922 13 9.4375C13.0499 9.38922 13.1068 9.33267 13.1768 9.2627L14.4697 7.96973Z"/><path d="M22 1.25C22.4142 1.25 22.75 1.58579 22.75 2C22.75 2.41421 22.4142 2.75 22 2.75H2C1.58579 2.75 1.25 2.41421 1.25 2C1.25 1.58579 1.58579 1.25 2 1.25H22Z"/>',
  format: '<path d="M3 10C3 6.22876 3 4.34315 4.17157 3.17157C5.34315 2 7.22876 2 11 2H13C16.7712 2 18.6569 2 19.8284 3.17157C21 4.34315 21 6.22876 21 10V14C21 17.7712 21 19.6569 19.8284 20.8284C18.6569 22 16.7712 22 13 22H11C7.22876 22 5.34315 22 4.17157 20.8284C3 19.6569 3 17.7712 3 14V10Z" opacity=".5"/><path d="M13 15.25C13.4142 15.25 13.75 15.5858 13.75 16C13.75 16.4142 13.4142 16.75 13 16.75H8C7.58579 16.75 7.25 16.4142 7.25 16C7.25 15.5858 7.58579 15.25 8 15.25H13Z"/><path d="M16 11.25C16.4142 11.25 16.75 11.5858 16.75 12C16.75 12.4142 16.4142 12.75 16 12.75H8C7.58579 12.75 7.25 12.4142 7.25 12C7.25 11.5858 7.58579 11.25 8 11.25H16Z"/><path d="M16 7.25C16.4142 7.25 16.75 7.58579 16.75 8C16.75 8.41421 16.4142 8.75 16 8.75H8C7.58579 8.75 7.25 8.41421 7.25 8C7.25 7.58579 7.58579 7.25 8 7.25H16Z"/>',
  check: '<path d="M21 15.9983V9.99826C21 7.16983 21 5.75562 20.1213 4.87694C19.3529 4.10856 18.175 4.01211 16 4H8C5.82497 4.01211 4.64706 4.10856 3.87868 4.87694C3 5.75562 3 7.16983 3 9.99826V15.9983C3 18.8267 3 20.2409 3.87868 21.1196C4.75736 21.9983 6.17157 21.9983 9 21.9983H15C17.8284 21.9983 19.2426 21.9983 20.1213 21.1196C21 20.2409 21 18.8267 21 15.9983Z" opacity=".5"/><path d="M14.4883 10.4521C14.791 10.1696 15.2652 10.1857 15.5479 10.4883C15.8304 10.791 15.8143 11.2652 15.5117 11.5479L11.2256 15.5479C10.9374 15.8168 10.4903 15.8168 10.2021 15.5479L8.48828 13.9482C8.18548 13.6656 8.16953 13.1915 8.45215 12.8887C8.73475 12.5859 9.2089 12.569 9.51172 12.8516L10.7139 13.9736L14.4883 10.4521Z"/><path d="M14.5 2C15.3284 2 16 2.67157 16 3.5V4.5C16 5.32843 15.3284 6 14.5 6H9.5C8.67157 6 8 5.32843 8 4.5V3.5C8 2.67157 8.67157 2 9.5 2H14.5Z"/>',
  veil: '<path d="M2.02639 9.5V8.75C2.10074 6.11064 2.38461 4.5451 3.46486 3.46484C4.92933 2.00041 7.28601 2 12 2C16.714 2 19.0707 2.00038 20.5352 3.46484C21.6154 4.5451 21.8993 6.11066 21.9737 8.75L22 9.5H9.00002V22L8.25002 21.9561C5.90966 21.8589 4.47508 21.5454 3.46486 20.5352C2.00041 19.0707 2.00002 16.714 2.00002 12C2.00002 11.3766 1.99956 10.7944 2.00295 10.25L2.02639 9.5Z" opacity=".5"/><path d="M2 12C2 16.714 2 19.0711 3.46447 20.5355C4.47468 21.5458 5.90962 21.8591 8.25 21.9563L9 22V10.25V9.5H2.02645L2.00339 10.25C2 10.7944 2 11.3766 2 12Z" opacity=".5"/><path d="M21.9971 10.25C22.0005 10.7944 22 11.3766 22 12C22 16.714 21.9996 19.0707 20.5352 20.5352C19.0707 21.9996 16.714 22 12 22C11.1815 22 9.68405 21.9999 9 21.9922V9.5H22L21.9971 10.25Z"/><path d="M6 5C6.55228 5 7 5.44772 7 6C7 6.55228 6.55228 7 6 7C5.44772 7 5 6.55228 5 6C5 5.44772 5.44772 5 6 5Z"/><path d="M9 5C9.55228 5 10 5.44772 10 6C10 6.55228 9.55228 7 9 7C8.44772 7 8 6.55228 8 6C8 5.44772 8.44772 5 9 5Z"/><path d="M12 5C12.5523 5 13 5.44772 13 6C13 6.55228 12.5523 7 12 7C11.4477 7 11 6.55228 11 6C11 5.44772 11.4477 5 12 5Z"/>',
};

function tasksHtml() {
  return `<section class="home-tasks" aria-labelledby="tasks-home-h">
    <h2 id="tasks-home-h" class="home-h">${esc(H().titles.tasks)}</h2>
    <div class="task-tiles">${H().tasks.map(t => {
      const it = ITEMS[t.tool];
      return `<a class="task-tile" href="${esc(itemHref(it))}" ${itemLinkAttrs(it)}>
        <span class="task-top"><span class="task-ic">${SOLAR[t.tool] ? `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${SOLAR[t.tool]}</svg>` : icon(it.icon)}</span>${it.free ? '<span class="badge">Free</span>' : ''}</span>
        <b class="task-name">${esc(it.label)}</b>
        <span class="task-hint">${esc(t.hint)}</span>${newTabNote(it)}
      </a>`;
    }).join('')}</div>
  </section>`;
}

function bindHome() {
  const ta = $('#qs-text');
  const refresh = () => {
    const has = !!(workDoc.file || workDoc.text.trim());
    $$('[data-act="qs-check"], [data-act="qs-humanize"]').forEach(b => { b.disabled = !has; });
  };
  // The pill grows with the text, up to ~8 lines
  const grow = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 218) + 'px'; ta.closest('.qs-field').classList.toggle('tall', ta.scrollHeight > 42); };
  if (ta) { grow(); ta.addEventListener('input', () => { workDoc.text = ta.value; workDoc.formatted = null; grow(); refresh(); }); }
  const take = (file) => {
    if (!file) return;
    if (!/\.(docx|pdf|txt)$/i.test(file.name)) { toast('Please choose a .docx, .pdf or .txt file'); return; }
    if (/\.txt$/i.test(file.name)) {
      const r = new FileReader();
      r.onload = () => { workDoc.text = String(r.result); workDoc.file = null; rerenderHomeKeepScroll('#qs-text'); };
      r.readAsText(file);
      return;
    }
    workDoc.file = { name: file.name, size: file.size, blob: file }; workDoc.formatted = null;
    rerenderHomeKeepScroll('[data-act="qs-check"]');
  };
  $('#qs-file')?.addEventListener('change', (e) => take(e.target.files[0]));
  const card = $('#qs');
  card?.addEventListener('dragover', (e) => { e.preventDefault(); card.classList.add('drag'); });
  card?.addEventListener('dragleave', (e) => { if (!card.contains(e.relatedTarget)) card.classList.remove('drag'); });
  card?.addEventListener('drop', (e) => { e.preventDefault(); card.classList.remove('drag'); take(e.dataTransfer.files[0]); });
  $('#doc-filter')?.addEventListener('change', (e) => { state.docFilter = e.target.value; rerenderDocs(); });
}

function rerenderHomeKeepScroll(focusSel) {
  const y = window.scrollY;
  $('#main').innerHTML = renderHome();
  bindHome();
  window.scrollTo(0, y);
  if (focusSel) $(focusSel)?.focus({ preventScroll: true });
}

// Text from Home goes straight into the tool and runs there
function homeSendTo(tool, { text, file, note, turnitin = false } = {}) {
  const body = (text ?? workDoc.text).trim();
  const f = file === undefined ? workDoc.file : file;
  if (tool === 'turnitin' && !f && body && !turnitin) {
    Object.assign(state.qd, { text: body, status: 'idle', result: null, error: '', note: note || 'Added from Home.', autoRun: true });
    state.detMode = 'quick';
    go('turnitin');
    return;
  }
  if (tool === 'turnitin') {
    state.detMode = 'turnitin';
    if (!state.signedIn) return openSignup({ intent: 'turnitin' });
    const blob = f?.blob || new File([body], 'Your text.txt', { type: 'text/plain' });
    Object.assign(toolState('turnitin'), {
      file: { name: blob.name, size: blob.size, blob, text: body || null },
      note: note || 'Added from Home.', autoRun: true,
    });
    go('turnitin');
    return;
  }
  const t = toolState('humanizer');
  Object.assign(t, { mode: 'paste', text: body, fileName: '', status: 'idle', result: null, note: note || 'Added from Home.', autoRun: !!body });
  if (!body && f?.blob) {
    t.note = 'Reading your file…';
    API.extractText(f.blob).then((extracted) => {
      Object.assign(t, { text: extracted.trim(), fileName: f.name, note: `Text from “${f.name}”.`, autoRun: !!extracted.trim() });
    }).catch((err) => { t.note = err.message || 'Could not read the uploaded file.'; })
      .finally(() => { if (currentRoute() === 'humanizer') render(); });
  }
  go('humanizer');
}

function homeAction(act, el) {
  switch (act) {
    case 'qs-upload': $('#qs-file').click(); break;
    case 'qs-remove-file': workDoc.file = null; rerenderHomeKeepScroll('#qs-text'); break;
    case 'qs-check': homeSendTo('turnitin'); break;
    case 'qs-humanize': homeSendTo('humanizer'); break;
    case 'history-all': state.historyAll = true; rerenderHomeKeepScroll('[data-act="history-less"]'); break;
    case 'history-less': state.historyAll = false; rerenderHomeKeepScroll('[data-act="history-all"]'); break;
    case 'topup':
      if (currentRoute() !== 'pricing') state.returnTo = currentRoute();   // come back here after buying
      go('pricing'); setTimeout(() => $('#payg')?.scrollIntoView({ block: 'start' }), 60); break;
    case 'credits-more': state.creditsAll = !state.creditsAll; rerenderHomeKeepScroll('[data-act="credits-more"]'); break;
    case 'continue': {
      const d = state.docs.find(x => x.id === el.dataset.id), n = nextStep(d);
      if (d.tool === 'assignment' && d.projectId) {
        const a = assignState();
        if (a.projectId !== d.projectId && !assignBusy(a)) {
          state.assign = newAssign();
          store.set(assignKey(), d.projectId);
        }
        go('assignment');
      } else if ((n.go === 'humanize' || n.go === 'recheck') && !d.text) {
        if (d.scanId) { state.scanCurrent = d.scanId; go('turnitin'); } else go(n.go === 'humanize' ? 'humanizer' : 'turnitin');
      } else if (n.go === 'humanize') homeSendTo('humanizer', { text: d.text, file: null, note: `From “${d.title}”.` });
      else if (n.go === 'recheck') homeSendTo('turnitin', { text: d.text, file: null, note: `From “${d.title}”.`, turnitin: !!d.scanId });
      else go(n.go === 'check' ? 'check' : n.go);
      break;
    }
  }
}

/* ---------- Humanizer & AI check (shared text tool) ---------- */
function renderTextTool(id) {
  const item = ITEMS[id], t = toolState(id), flow = CONFIG.flows[id];
  const tourName = Object.keys(CONFIG.tours).find(k => CONFIG.tours[k].route === item.route);
  return `<div class="page page-hum">
    ${pageHead(item, '', tourName ? `<button class="btn btn-sm" data-act="start-tour" data-tour-name="${tourName}">${icon('help')} Take the tour</button>` : '')}
    <section class="card hum-card" aria-label="Input">
      <div id="hum-input">
      <div class="seg" role="tablist" aria-label="Input type">
        <button role="tab" id="tab-paste" aria-controls="panel-paste" aria-selected="${t.mode === 'paste'}" tabindex="${t.mode === 'paste' ? 0 : -1}" data-mode="paste">Paste text</button>
        <button role="tab" id="tab-file" aria-controls="panel-file" aria-selected="${t.mode === 'file'}" tabindex="${t.mode === 'file' ? 0 : -1}" data-mode="file">File</button>
      </div>
      ${t.note ? `<p class="note">${esc(t.note)}</p>` : ''}
      <div id="panel-paste" role="tabpanel" aria-labelledby="tab-paste" ${t.mode !== 'paste' ? 'hidden' : ''}>
        <label class="visually-hidden" for="tool-text">Your text</label>
        <textarea class="input" id="tool-text" placeholder="Paste your text here…">${esc(t.text)}</textarea>
      </div>
      <div id="panel-file" role="tabpanel" aria-labelledby="tab-file" ${t.mode !== 'file' ? 'hidden' : ''}>
        <button type="button" class="dropzone" id="dropzone">
          ${icon('upload')}
          <strong>${t.fileName ? esc(t.fileName) : 'Drop a file here or click to upload'}</strong>
          <span class="small">.txt, .docx, .pdf · up to ${fmtNum(CONFIG.wordLimit)} words${t.fileName ? ' · click to replace' : ''}</span>
        </button>
        <input type="file" id="file-input" accept=".txt,.doc,.docx,.pdf" hidden>
      </div>
      </div>
      <div class="tool-bar">
        <span class="tool-meta" id="hum-meta">
          <span class="counter" id="counter" aria-live="polite"></span>
          <span class="cost" id="cost">Cost: ${state.signedIn && !item.free && estCredits(id) != null ? estLabel(id) : costHtml(item)}</span>
          ${state.signedIn && id === 'humanizer' && CONFIG.freeHumanize ? `<span class="free">${esc(freeHumanizeNote(true))}</span>` : ''}
        </span>
        <span class="spacer"></span>
        <button class="btn" data-act="clear-tool">Clear</button>
        <button class="btn btn-primary" data-act="run" id="run-btn">${icon('sparkles')} ${esc(flow.runLabel)}</button>
      </div>
    </section>
    <section class="result" id="result" aria-live="polite">${resultHtml(id)}</section>
  </div>`;
}

function resultHtml(id) {
  const t = toolState(id), flow = CONFIG.flows[id];
  if (t.status === 'loading') return `<div class="card hum-result loading"><span class="spinner" aria-hidden="true"></span>${esc(flow.loadingLabel)}</div>`;
  if (t.status === 'error') return `<div class="card hum-result" role="alert">
    <div class="result-head">
      <h2>Couldn’t humanize the text</h2>
      <span class="spacer"></span>
      ${t.error.action === 'topup' ? '<button class="btn btn-sm btn-primary" data-act="topup">Top up credits</button>' : '<button class="btn btn-sm" data-act="run">Try again</button>'}
    </div>
    <p class="muted" style="margin:0">${esc(t.error.message)}</p>
  </div>`;
  if (t.status !== 'done') return '';
  // Result actions: main = send the text to the AI Detector, secondary = Copy for pasted text,
  // or a download menu (copy / pdf / docx / txt) when the text came from an uploaded file
  const fmts = [['pdf', 'PDF document', '#e5252a'], ['docx', 'Word document', '#2b579a'], ['txt', 'Plain text', '#71717a']];
  // File-type icon: a page with a folded corner and a coloured format badge
  const fileIc = (ext, c) => `<svg class="dl-file" viewBox="0 0 24 28" aria-hidden="true"><path d="M4 1h11l6 6v18a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2z" fill="var(--surface)" stroke="color-mix(in oklab, var(--text) 25%, transparent)"/><path d="M15 1v6h6" fill="none" stroke="color-mix(in oklab, var(--text) 25%, transparent)"/><rect x="0" y="14" width="${ext.length > 3 ? 24 : 20}" height="9" rx="2" fill="${c}"/><text x="${ext.length > 3 ? 12 : 10}" y="20.8" text-anchor="middle" font-size="6.4" font-weight="700" fill="#fff" font-family="system-ui, sans-serif">${ext.toUpperCase()}</text></svg>`;
  return `<div class="card hum-result">
    <div class="result-head">
      <h2>${esc(flow.resultTitle)}</h2>
      <span class="spacer"></span>
      ${!t.result.file ? '<button class="btn btn-sm" data-act="copy">Copy</button>' : `<div class="dl-wrap">
        <button class="btn btn-sm" data-act="dl-toggle" aria-haspopup="menu" aria-expanded="false">${icon('download')} Download ${icon('chevronDown')}</button>
        <div class="dl-menu" role="menu">
          <button role="menuitem" data-act="copy"><b>${icon('copy')}</b><span>Copy text</span></button>
          <hr>
          ${fmts.map(([ext, label, c]) => `<button role="menuitem" data-act="dl-as" data-value="${ext}"><b>${fileIc(ext, c)}</b><span>${label}</span></button>`).join('')}
        </div>
      </div>`}
      <button class="btn btn-sm btn-primary" data-act="next">${esc(flow.next.label)}</button>
    </div>
    <pre class="result-text" id="result-text">${esc(t.result.text)}</pre>
  </div>`;
}

/* ---------- Veil ---------- */
/* ---------- Assignment: one input → parsed brief + price → chat ---------- */
// phase: input → priced → running → done | error | refunded. The pipeline is driven from this tab, step by step.
const newAssign = () => ({ stage: 'input', files: [], text: '', messages: [], brief: null, briefBase: null, confirmed: false,
  loading: false, loadingLabel: '', projectId: null, pricing: null, saving: false, phase: 'input', progress: null,
  error: null, running: false, outline: [], revisions: null, briefSource: null, hydrated: false });
const assignState = () => state.assign || (state.assign = newAssign());
const assignKey = () => 'assign-' + (BOOT.user ? BOOT.user.id : 'guest');
const fmtSize = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB');

function assignStep(a) { return a.stage === 'input' ? 0 : a.confirmed ? 2 : 1; }

function renderAssignment() {
  const a = assignState();
  return `<div class="page assign" id="assign-page">
    ${pageHead(ITEMS.assignment, '', `<div class="assign-head-actions">
        <button class="btn btn-sm" data-act="start-tour" data-tour-name="assignment">${icon('help')} How it works</button>
        ${a.messages.length ? `<button class="btn btn-sm" data-act="assign-new" ${assignBusy(a) ? 'disabled' : ''}>${icon('plus')} New chat</button>` : ''}
      </div>`)}
    <div class="assign-thread ${a.messages.length ? '' : 'empty'}" id="assign-thread">
      ${a.messages.length ? assignChatHtml(a) : assignEmptyHtml()}
    </div>
    ${assignComposerHtml(a)}
    <div class="assign-drop-overlay" aria-hidden="true">${icon('upload')} Drop files to attach</div>
  </div>`;
}

function fileChipsHtml(files, removable) {
  if (!files.length) return '';
  return `<ul class="file-chips">${files.map((f, i) => `<li class="file-chip">
    ${icon('file')}<span class="file-name">${esc(f.name)}</span>${f.size ? `<span class="muted small">${fmtSize(f.size)}</span>` : ''}
    ${removable ? `<button type="button" class="chip-x" data-act="assign-remove-file" data-i="${i}" aria-label="Remove ${esc(f.name)}">${icon('close')}</button>` : ''}
  </li>`).join('')}</ul>`;
}

// Empty chat: what this is, what to attach, examples
function assignEmptyHtml() {
  const C = CONFIG.assignment;
  return `<div class="assign-welcome">
      <span class="assign-welcome-icon" aria-hidden="true">${icon('file')}</span>
      <h1>${esc(C.title)}</h1>
      <p class="lead">${esc(C.subtitle)}</p>
      <p class="small muted" style="margin:0">Attach with + or drop files anywhere here · ${esc(C.formats)}, up to ${esc(C.maxFileSizeMb)} MB</p>
      <div class="examples">
        <span class="small muted" id="examples-h">Or start from an example</span>
        <div class="chips" role="group" aria-labelledby="examples-h">
          ${C.examples.map((e, i) => `<button type="button" class="chip" data-act="assign-example" data-i="${i}">${esc(e.label)}</button>`).join('')}
        </div>
      </div>
    </div>`;
}

function assignChatHtml(a) {
  const msgs = a.messages.map(m => {
    if (m.role === 'user') return `<div class="msg msg-user"><div class="msg-bubble">
        ${fileChipsHtml(m.files || [], false)}${m.text ? `<p>${esc(m.text)}</p>` : ''}</div></div>`;
    if (m.role === 'brief') return serviceMsg(briefCardHtml(a));
    if (m.role === 'progress') return serviceMsg(`<div class="msg-bubble service" id="assign-progress">${assignProgressInner(a)}</div>`);
    return serviceMsg(`<div class="msg-bubble service">${m.html}</div>`);
  }).join('');
  const loading = a.loading ? serviceMsg(`<div class="msg-bubble service loading"><span class="spinner" aria-hidden="true"></span>${esc(a.loadingLabel || 'Thinking…')}</div>`) : '';
  return `<div class="chat" id="chat" aria-live="polite">${msgs}${loading}</div>`;
}

// One composer for the whole chat: first message = the brief (gets a price), then follow-up requests
function assignComposerHtml(a) {
  const C = CONFIG.assignment, first = !a.brief, busy = assignBusy(a);
  const ready = a.files.length > 0 || a.text.trim().length > 0;
  const note = first ? 'You see the price before you pay. Nothing is charged until you confirm.'
    : a.phase === 'running' ? 'Writing your assignment. You can ask for changes when it’s ready.'
    : a.phase === 'done' ? `Edits to the draft are part of this assignment${a.revisions ? ` (${a.revisions.used} of ${a.revisions.max} free rounds used)` : ''}.`
    : a.confirmed ? 'Retry above to continue your assignment.'
    : 'Add details or files to update the brief before you confirm.';
  return `<form class="assign-composer" id="assign-composer" aria-label="${first ? 'Your assignment brief' : 'Message'}">
    ${a.brief ? `<div class="chips assign-quick" role="group" aria-label="Quick requests">
        ${C.refinements.map(r => `<button type="button" class="chip" data-act="assign-refine" ${busy ? 'disabled' : ''}>${esc(r)}</button>`).join('')}</div>` : ''}
    <div class="cmp-box">
      ${fileChipsHtml(a.files, true)}
      <div class="cmp-row">
        <button type="button" class="icon-btn cmp-attach" data-act="assign-upload" aria-label="Attach files"
          data-tip-title="Attach files" data-tip-desc="${esc(C.formats)}" data-tip-pos="bottom">${icon('plus')}</button>
        <label class="visually-hidden" for="assign-msg">${first ? 'Describe your assignment' : 'Message'}</label>
        <textarea id="assign-msg" class="cmp-input" rows="1" placeholder="${first ? esc(C.composerPlaceholder) : 'Ask to change something: shorten, add sources…'}">${esc(a.text)}</textarea>
        <button type="submit" class="sl-send" id="assign-send" ${ready && !busy ? '' : 'disabled'}
          aria-label="${first ? 'Get price' : 'Send'}" data-tip-title="${first ? 'Get price' : 'Send'}" data-tip-desc="" data-tip-pos="bottom">${icon('send')}</button>
      </div>
    </div>
    <p class="small muted cmp-note">${note}</p>
    <input type="file" id="assign-file" multiple accept=".pdf,.doc,.docx,.txt,image/*" hidden>
  </form>`;
}

function serviceMsg(inner) {
  return `<div class="msg msg-service"><span class="avatar logo-mark" aria-hidden="true">${LOGO_SVG}</span><div class="msg-main">${inner}</div></div>`;
}

function briefCardHtml(a) {
  const C = CONFIG.assignment, b = a.brief, locked = a.confirmed || a.phase === 'running';
  const field = (f) => {
    const id = 'brief-' + f.key, v = b[f.key] || '', dis = locked || f.readonly ? 'disabled' : '';
    let control;
    if (f.options) {
      const opts = v && !f.options.includes(v) ? [...f.options, v] : f.options;
      control = `<select class="select" id="${id}" data-brief="${f.key}" ${dis}>${opts.map(o => `<option ${o === v ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
    }
    else if (f.multiline) control = `<textarea class="input field-input" id="${id}" rows="3" data-brief="${f.key}" ${dis}>${esc(v)}</textarea>`;
    else control = `<input class="input field-input" id="${id}" data-brief="${f.key}" value="${esc(v)}" ${dis}>`;
    return `<div class="field ${f.multiline ? 'field-wide' : ''}"><label for="${id}">${esc(f.label)}</label>${control}</div>`;
  };
  const balance = state.signedIn
    ? `Your balance: ${state.balance} credits`
    : `Sign up to get ${CONFIG.signupCredits} credits`;
  return `<section class="card brief-card" aria-labelledby="brief-h">
    <h2 id="brief-h" tabindex="-1">Parsed brief</h2>
    <p class="muted small" style="margin-top:0">${a.confirmed ? 'Confirmed. You can still ask for changes in the chat below.' : 'Here is what we understood. Fix anything we got wrong before you confirm.'}</p>
    <div class="brief-grid">${C.briefFields.map(field).join('')}</div>
    <div class="price-box">
      <div>
        <div class="muted small">Price</div>
        <div class="price" id="assign-price">${esc(assignPriceLabel(a))}</div>
        <div class="small muted">${balance}</div>
      </div>
      ${a.confirmed
        ? '<span class="status-pill on">Confirmed</span>'
        : `<div class="price-actions">
             <button class="btn btn-primary" id="assign-confirm-btn" data-act="assign-confirm" ${a.saving || a.loading ? 'disabled' : ''}>${state.signedIn ? 'Confirm and continue' : 'Sign up to continue'}</button>
             <span class="small muted">You pay only after confirming</span>
           </div>`}
    </div>
  </section>`;
}

const ASSIGN_STYLES = { apa: 'APA 7', harvard: 'Harvard', mla: 'MLA 9', chicago: 'Chicago' };

// The brief card fields from the server's requirement analysis
function briefFromProject(d) {
  const r = d.requirement || {}, art = (d.project && d.project.artifacts) || {};
  const key = String(r.citation_style || '').toLowerCase().match(/apa|harvard|mla|chicago/);
  const summary = [
    (r.required_sections || []).length ? 'Sections: ' + r.required_sections.join(', ') : '',
    r.minimum_sources ? `At least ${r.minimum_sources} sources` : '',
    ...(r.learning_outcomes || []).slice(0, 4),
  ].filter(Boolean).join('\n');
  return {
    type: r.assignment_type || '',
    length: r.word_count ? `${r.word_count} words` : '',
    style: key ? ASSIGN_STYLES[key[0]] : (r.citation_style || 'Not specified'),
    deadline: r.deadline || '',
    language: 'English',
    requirements: art.brief_instructions || summary,
  };
}

function assignApplyProject(a, d) {
  const art = (d.project && d.project.artifacts) || {};
  a.pricing = art.pricing || a.pricing;
  a.brief = briefFromProject(d);
  a.briefBase = { ...a.brief };
  a.phase = a.confirmed ? a.phase : 'priced';
}

const assignPriceLabel = (a) => (a.saving ? 'Updating…' : a.pricing && a.pricing.amount_coins != null ? `${a.pricing.amount_coins} credits` : '—');
const assignBusy = (a) => a.loading || a.saving || a.running || a.phase === 'running';
const onAssignPage = () => currentRoute() === 'assignment';

// Update the price box in place so the field the student moved to keeps focus
function assignPaintBrief() {
  const a = assignState(), price = $('#assign-price'), btn = $('#assign-confirm-btn');
  if (price) price.textContent = assignPriceLabel(a);
  if (btn) btn.disabled = a.saving || a.loading;
  const len = $('#brief-length');
  if (len && document.activeElement !== len && a.brief) len.value = a.brief.length;
}

function assignErrorHtml(message, actions = '') {
  return `<p class="field-err" role="alert" style="margin:0 0 var(--space-2)">${esc(message)}</p>${actions ? `<div class="chips">${actions}</div>` : ''}`;
}

function rerenderAssign(focusSel) {
  $('#main').innerHTML = renderAssignment();
  bindAssignment();
  const el = focusSel && $(focusSel);
  if (el) {
    el.focus({ preventScroll: true });
    if (el.tagName === 'TEXTAREA') el.setSelectionRange(el.value.length, el.value.length);
  }
  // Keep the newest message in view, like a chat
  if (assignState().messages.length) window.scrollTo(0, document.body.scrollHeight);
}

function bindAssignment() {
  const a = assignState(), page = $('#assign-page'), msg = $('#assign-msg'), send = $('#assign-send');
  $$('[data-brief]').forEach(el => {
    el.addEventListener('input', () => { a.brief[el.dataset.brief] = el.value; });
    el.addEventListener('change', () => { a.brief[el.dataset.brief] = el.value; assignSaveBrief(); });
  });
  const grow = () => { msg.style.height = 'auto'; msg.style.height = Math.min(msg.scrollHeight, 220) + 'px'; };
  grow();
  msg.addEventListener('input', () => {
    a.text = msg.value; grow();
    send.disabled = !(a.files.length || a.text.trim()) || assignBusy(a);
  });
  msg.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); assignSend(); } });
  $('#assign-composer').addEventListener('submit', (e) => { e.preventDefault(); assignSend(); });
  // Files: "+" button or drag and drop anywhere on the page
  const input = $('#assign-file');
  const addFiles = (list) => {
    if (!list.length) return;
    const maxBytes = CONFIG.assignment.maxFileSizeMb * 1048576;
    const total = [...a.files, ...list].reduce((s, f) => s + (f.size || 0), 0);
    if (total > maxBytes) { toast(`Files are too large: up to ${CONFIG.assignment.maxFileSizeMb} MB in total.`); return; }
    a.files.push(...[...list].map(f => ({ name: f.name, size: f.size, blob: f })));
    rerenderAssign('#assign-msg');
  };
  input.addEventListener('change', () => addFiles(input.files));
  page.addEventListener('dragover', (e) => { e.preventDefault(); page.classList.add('drag'); });
  page.addEventListener('dragleave', (e) => { if (!page.contains(e.relatedTarget)) page.classList.remove('drag'); });
  page.addEventListener('drop', (e) => { e.preventDefault(); page.classList.remove('drag'); addFiles(e.dataTransfer.files); });
  const saved = store.get(assignKey(), null);
  if (state.signedIn && saved && !a.projectId && !a.messages.length && !a.hydrated) assignHydrate(saved);
}

const assignUserMsg = (source) => ({ role: 'user', files: source.files.map(({ name, size }) => ({ name, size })), text: source.text });
const assignErrMsg = (err) => (err && err.status >= 500
  ? 'Something went wrong on our side. Try again in a moment.'
  : apiErrorInfo(err, { intent: 'assignment' }).message);

function assignSend() {
  const a = assignState();
  if (assignBusy(a) || !(a.files.length || a.text.trim())) return;
  if (!a.brief) assignGetPrice(); else sendAssignMessage(a.text);
}

function assignGetPrice() {
  const a = assignState();
  if (!state.signedIn) {
    openSignup({ intent: 'assignment', lead: `Create a free account to see your price. You get ${CONFIG.signupCredits} credits.` });
    return;
  }
  const source = { text: a.text.trim(), files: [...a.files] };
  a.messages.push(assignUserMsg(source));
  a.text = ''; a.files = [];
  assignPrice(a, source);
}

// Upload the brief (once per project), let the server read it, then price it
async function assignPrice(a, source) {
  a.briefSource = source;
  a.stage = 'chat'; a.loading = true; a.loadingLabel = 'Reading your brief…';
  a.messages = a.messages.filter(m => !m.retryPrice && m.role !== 'brief');
  rerenderAssign('#assign-msg');
  try {
    if (!a.projectId) {
      const up = await API.assignment.upload({ files: source.files.map(f => f.blob).filter(Boolean), note: source.text });
      a.projectId = up.project.id;
      store.set(assignKey(), a.projectId);
    }
    await API.assignment.analyze(a.projectId);
    assignApplyProject(a, await API.assignment.price(a.projectId));
    a.messages.push({ role: 'brief' });
  } catch (err) {
    const e = apiErrorInfo(err, { intent: 'assignment' });
    if (!e.handled) a.messages.push({ role: 'assistant', retryPrice: true,
      html: assignErrorHtml(assignErrMsg(err), '<button type="button" class="btn btn-sm" data-act="assign-retry-price">Try again</button>') });
  } finally {
    a.loading = false;
    if (onAssignPage()) rerenderAssign(a.brief ? '#brief-h' : '#assign-msg');
  }
}

// Corrections in the brief card: the server stores them and returns the new price
async function assignSaveBrief() {
  const a = assignState(), b = a.brief, base = a.briefBase;
  if (!a.projectId || a.confirmed || !b || !base) return;
  if (a.saving) { a.briefDirty = true; return; }
  const fields = {};
  if (b.type !== base.type) fields.assignment_type = b.type;
  if (b.length !== base.length) {
    const words = parseInt(String(b.length).replace(/[^\d]/g, ''), 10);
    if (!words) { a.brief.length = base.length; assignPaintBrief(); toast('Enter the length as a number of words.'); return; }
    fields.word_count = words;
  }
  if (b.style !== base.style) fields.citation_style = b.style === 'Not specified' ? '' : b.style;
  if (b.deadline !== base.deadline) fields.deadline = b.deadline;
  if (b.requirements !== base.requirements) fields.instructions = b.requirements;
  if (!Object.keys(fields).length) return;
  a.saving = true; a.briefDirty = false;
  assignPaintBrief();
  let failed = false;
  try {
    assignApplyProject(a, await API.assignment.brief(a.projectId, fields));
  } catch (err) {
    failed = true;
    a.brief = { ...base };
    toast(assignErrMsg(err));
  } finally {
    a.saving = false;
    if (failed && onAssignPage()) rerenderAssign('#brief-h'); else assignPaintBrief();
    if (a.briefDirty) assignSaveBrief();
  }
}

async function assignConfirm() {
  const a = assignState();
  if (!state.signedIn) return signUp();
  if (!a.projectId || a.confirmed || a.saving || a.loading) return;
  a.loading = true; a.loadingLabel = 'Confirming…';
  rerenderAssign();
  try {
    const d = await API.assignment.confirm(a.projectId);
    if (typeof d.balance === 'number') state.balance = d.balance;
    a.confirmed = true;
    const mins = a.pricing && a.pricing.estimated_minutes;
    a.messages.push({ role: 'assistant', html: `<p>${d.coins_charged ? `${d.coins_charged} credits charged. ` : ''}Writing your ${esc((a.brief.type || 'assignment').toLowerCase())} now: research, structure, writing, citations and formatting${mins ? `. This takes about ${mins} minutes` : ''}.</p>
      <p class="muted small" style="margin-bottom:0">Keep this tab open. If you close it, open Assignment again and it continues where it stopped.</p>` });
    a.messages.push({ role: 'progress' });
    renderHeader();
    assignRun(a);
  } catch (err) {
    const e = apiErrorInfo(err, { intent: 'assignment' });
    if (!e.handled) a.messages.push({ role: 'assistant', html: assignErrorHtml(assignErrMsg(err),
      e.action === 'topup' ? '<button type="button" class="btn btn-sm btn-primary" data-act="assign-topup">Buy credits</button>' : '') });
  } finally {
    a.loading = false;
    if (onAssignPage()) rerenderAssign('#assign-msg');
  }
}

function sendAssignMessage(text) {
  const a = assignState();
  text = text.trim();
  const files = [...a.files];
  if ((!text && !files.length) || assignBusy(a)) return;
  if (a.phase === 'done') return assignRevise(a, text, files);
  if (a.confirmed) return;
  a.text = ''; a.files = [];
  if (files.length) {
    // New files change the brief, so it is read and priced again as a new project
    const prev = a.briefSource || { text: '', files: [] };
    if (prev.files.some(f => !f.blob)) {
      a.files = files; a.text = text;
      toast('To change the files of this brief, start a new chat.');
      return;
    }
    a.messages.push(assignUserMsg({ text, files }));
    Object.assign(a, { projectId: null, brief: null, briefBase: null, pricing: null });
    store.set(assignKey(), null);
    assignPrice(a, { text: [prev.text, text].filter(Boolean).join('\n\n'), files: [...prev.files, ...files] });
    return;
  }
  a.messages.push(assignUserMsg({ text, files: [] }));
  a.brief.requirements = [a.brief.requirements, text].filter(Boolean).join('\n');
  a.messages.push({ role: 'assistant', html: '<p>Added to the key requirements in the brief above.</p>' });
  rerenderAssign('#assign-msg');
  assignSaveBrief();
}

async function assignRevise(a, text, files) {
  if (files.length) toast('Files can’t be added after the draft is written. Describe the change instead.');
  if (!text) return;
  a.text = ''; a.files = [];
  a.messages.push(assignUserMsg({ text, files: [] }));
  a.loading = true; a.loadingLabel = 'Applying your changes…';
  rerenderAssign('#assign-msg');
  try {
    const r = await API.assignment.revise(a.projectId, text);
    a.revisions = { used: r.rounds_used, max: r.max_rounds };
    a.messages.push({ role: 'assistant', html: `<p>${esc(r.assistant_reply || 'Updated your assignment.')}</p>
      <button class="btn btn-sm" data-act="assign-download">${icon('download')} Download updated file</button>` });
  } catch (err) {
    a.messages.push({ role: 'assistant', html: assignErrorHtml(assignErrMsg(err)) });
  } finally {
    a.loading = false;
    if (onAssignPage()) rerenderAssign('#assign-msg');
  }
}

/* The writing pipeline, step by step. Every step is skipped when the server already has its result,
   so Retry and reopening the page continue where it stopped. */
const ASSIGN_STEPS = {
  research:   ['Researching sources', 2, 10],
  blueprint:  ['Planning the structure', 10, 16],
  writer:     ['Writing', 16, 62],
  citations:  ['Adding citations', 62, 66],
  humanizer:  ['Polishing the wording', 66, 86],
  format:     ['Formatting', 86, 90],
  review:     ['Checking quality', 90, 95],
  validation: ['Checking the requirements', 95, 97],
  delivery:   ['Preparing your file', 97, 100],
};

function assignProgressInner(a) {
  if (a.phase === 'done') {
    const outline = a.outline.length ? `<ol class="outline">${a.outline.map(o => `<li>${esc(o)}</li>`).join('')}</ol>` : '';
    const left = a.revisions ? Math.max(0, a.revisions.max - a.revisions.used) : null;
    return `<p>Your ${esc(((a.brief && a.brief.type) || 'assignment').toLowerCase())} is ready.${outline ? ' Here is the structure:' : ''}</p>${outline}
      <button class="btn btn-sm btn-primary" data-act="assign-download">${icon('download')} Download</button>
      <p class="muted small" style="margin:var(--space-2) 0 0">Ask for changes below${left != null ? ` (${left} free revision round${left === 1 ? '' : 's'} left)` : ''}.</p>`;
  }
  if (a.phase === 'refunded') {
    return `<p style="margin:0">This assignment was stopped and ${a.refundCoins ? `${a.refundCoins} credits were` : 'your credits were'} returned to your balance. Start a new chat to try again.</p>`;
  }
  if (a.phase === 'error') {
    return assignErrorHtml(a.error || 'Something went wrong.',
      `<button type="button" class="btn btn-sm btn-primary" data-act="assign-retry">Retry</button>
       <button type="button" class="btn btn-sm" data-act="assign-refund">Stop and return my credits</button>`);
  }
  const p = a.progress || { label: 'Starting', pct: 1, detail: '' };
  return `<div style="display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap"><span class="spinner" aria-hidden="true"></span>
      <strong>${esc(p.label)}…</strong>${p.detail ? `<span class="muted small">${esc(p.detail)}</span>` : ''}</div>
    <div class="meter-bar" role="progressbar" aria-label="Assignment progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${p.pct}"><span style="width:${p.pct}%"></span></div>
    <p class="muted small" style="margin:var(--space-2) 0 0">${p.pct}% done</p>`;
}

function assignSetStep(a, step, frac = 0, detail = '') {
  const [label, from, to] = ASSIGN_STEPS[step];
  a.progress = { label, detail, pct: Math.round(from + (to - from) * Math.max(0, Math.min(1, frac))) };
  const el = onAssignPage() && state.assign === a && $('#assign-progress');
  if (el) el.innerHTML = assignProgressInner(a);
}

const assignTransient = (err) => !!err && (err.code === 'NETWORK' || [502, 503, 504].includes(err.status));
async function assignTry(fn, attempts = 2) {
  for (let i = 1; ; i++) {
    try { return await fn(); } catch (err) {
      if (!assignTransient(err) || i >= attempts) throw err;
      await new Promise(r => setTimeout(r, 1500 * i));
    }
  }
}
const writerSectionsDone = (s) => !!s && (s.sections || []).length > 0 && s.sections.every(x => x.status === 'completed');
const humanizerFinished = (s) => !!s && (s.status === 'completed' || s.status === 'merged');

async function assignRun(a) {
  if (a.running || !a.projectId) return;
  const id = a.projectId, P = API.assignment;
  const step = (path, body, attempts = 2) => assignTry(() => P.step(id, path, body), attempts);
  a.running = true; a.phase = 'running'; a.error = null;
  if (onAssignPage() && state.assign === a) rerenderAssign();
  assignSetStep(a, 'research');
  try {
    let d = await assignTry(() => P.get(id));
    const art = (d.project && d.project.artifacts) || {};
    let research = d.research_plan;
    if (!research) { assignSetStep(a, 'research'); research = (await step('/research')).research_plan || null; }
    if (!d.blueprint) { assignSetStep(a, 'blueprint'); await step('/blueprint', { research_plan: research }); }

    let ws = d.writer_session;
    if (!(ws && ws.status === 'merged')) {
      if (!ws) { assignSetStep(a, 'writer'); ws = await step('/writer/start'); }
      const total = (ws.sections || []).length;
      let guard = 0, last = -1, stale = 0;
      while (!writerSectionsDone(ws)) {
        const done = (ws.completed_section_ids || []).length;
        if (done === last) { if (++stale >= 3) throw new Error('Writing stalled. Press Retry to continue.'); } else { stale = 0; last = done; }
        if (++guard > Math.max(20, total * 4 + 5)) throw new Error('Writing is taking too long. Press Retry to continue.');
        assignSetStep(a, 'writer', total ? done / total : 0, total ? `section ${Math.min(done + 1, total)} of ${total}` : '');
        // Single attempt: a client retry would race the request still running on the server
        ws = await P.step(id, '/writer/advance', { writer_session: ws });
      }
      assignSetStep(a, 'writer', 1);
      await P.step(id, '/writer/merge', { writer_session: ws });
    }

    if (!art.citation_pack) { assignSetStep(a, 'citations'); await step('/citations/generate'); }

    let hs = d.humanizer_session;
    if (!(hs && hs.status === 'merged')) {
      if (!hs) { assignSetStep(a, 'humanizer'); hs = await step('/humanizer/start'); }
      const max = Math.max(20, (hs.total_paragraphs || (hs.paragraphs || []).length || 1) * 5);
      let guard = 0;
      while (!humanizerFinished(hs)) {
        if (++guard > max) throw new Error('Polishing is taking too long. Press Retry to continue.');
        const paras = hs.paragraphs || [];
        const done = paras.filter(p => p && (p.status === 'completed' || p.status === 'passed')).length;
        assignSetStep(a, 'humanizer', paras.length ? done / paras.length : 0, paras.length ? `paragraph ${Math.min(done + 1, paras.length)} of ${paras.length}` : '');
        hs = await step('/humanizer/advance', { humanizer_session: hs });
      }
      await step('/humanizer/merge', { humanizer_session: hs });
    }

    if (!art.formatted_document) { assignSetStep(a, 'format'); await step('/format'); }
    if (!d.review_report) {
      assignSetStep(a, 'review');
      const review = (await step('/review')).review_report || null;
      try { await step('/revision', { review_report: review }, 1); } catch { /* best effort: never blocks delivery */ }
    }
    if (!art.validation_report) { assignSetStep(a, 'validation'); await step('/validate-requirements'); }
    if (!d.delivery_package) { assignSetStep(a, 'delivery'); await step('/delivery'); }

    d = await assignTry(() => P.get(id));
    a.outline = ((d.blueprint && d.blueprint.sections) || []).map(s => s.title).filter(Boolean);
    a.phase = 'done';
    if (!state.docs.some(x => x.projectId === id)) addDoc(d.project.title || (a.brief && a.brief.type) || 'Assignment', 'assignment', { projectId: id });
    if (!onAssignPage()) toast('Your assignment is ready. Open Assignment to download it.');
  } catch (err) {
    a.phase = 'error';
    a.error = err && err.status >= 500 ? 'Something went wrong on our side. Press Retry to continue.' : assignErrMsg(err);
  } finally {
    a.running = false;
    loadCredits();
    if (onAssignPage() && state.assign === a) rerenderAssign();
  }
}

async function assignRefund() {
  const a = assignState();
  if (!a.projectId || a.running) return;
  try {
    const r = await API.assignment.refund(a.projectId);
    if (typeof r.balance === 'number') state.balance = r.balance;
    a.refundCoins = r.coins_refunded || 0;
    a.phase = 'refunded';
    store.set(assignKey(), null);
    renderHeader();
    loadCredits();
  } catch (err) {
    toast(assignErrMsg(err));
  }
  if (onAssignPage()) rerenderAssign();
}

async function assignDownload(btn) {
  const a = assignState();
  if (!a.projectId) return;
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(API.assignment.downloadUrl(a.projectId), { credentials: 'same-origin' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(res.status >= 500 ? 'The file isn’t ready yet. Try again in a moment.' : (data.error || `Download failed (HTTP ${res.status})`));
    }
    const name = (res.headers.get('Content-Disposition') || '').match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i);
    const link = document.createElement('a');
    link.href = URL.createObjectURL(await res.blob());
    link.download = name ? decodeURIComponent(name[1]) : 'Assignment.docx';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Reopen the last assignment of this account (after a reload or from Home)
async function assignHydrate(id) {
  const a = assignState();
  Object.assign(a, { hydrated: true, loading: true, loadingLabel: 'Loading your assignment…', stage: 'chat' });
  rerenderAssign();
  try {
    const d = await API.assignment.get(id);
    const art = (d.project && d.project.artifacts) || {}, r = d.requirement || {};
    a.projectId = id;
    const files = (d.files || []).map(f => ({ name: f.original_filename || 'file' })).filter(f => f.name !== 'project_note.txt');
    const text = art.original_note != null ? art.original_note : (d.project.note || '');
    a.briefSource = { text, files };
    a.messages = [{ role: 'user', files, text }];
    if (!(r.analyzed_at || r.assignment_type) || !art.pricing) {
      a.messages.push({ role: 'assistant', retryPrice: true,
        html: assignErrorHtml('We didn’t finish reading this brief.', '<button type="button" class="btn btn-sm" data-act="assign-retry-price">Try again</button>') });
    } else {
      a.confirmed = !!(art.payment_confirmed || art.payment_refunded);
      assignApplyProject(a, d);
      a.messages.push({ role: 'brief' });
      if (art.payment_refunded) {
        Object.assign(a, { phase: 'refunded', refundCoins: art.payment_refund_coins || 0 });
        a.messages.push({ role: 'progress' });
      } else if (art.payment_confirmed) {
        a.messages.push({ role: 'progress' });
        if (d.delivery_package) {
          a.phase = 'done';
          a.outline = ((d.blueprint && d.blueprint.sections) || []).map(s => s.title).filter(Boolean);
          const rc = await API.assignment.revisions(id).catch(() => null);
          if (rc) {
            a.revisions = { used: rc.rounds_used, max: rc.max_rounds };
            (rc.messages || []).forEach(m => a.messages.push(m.role === 'user'
              ? { role: 'user', files: [], text: m.content || '' }
              : { role: 'assistant', html: `<p>${esc(m.content || '')}</p>` }));
          }
        } else {
          a.phase = 'running';
        }
      }
    }
  } catch (err) {
    if (err.status === 403 || err.status === 404) {
      store.set(assignKey(), null);
      state.assign = Object.assign(newAssign(), { hydrated: true });
    } else {
      toast(assignErrMsg(err));
    }
  } finally {
    const cur = assignState();
    cur.loading = false;
    if (onAssignPage()) rerenderAssign();
    if (cur.phase === 'running' && !cur.running) assignRun(cur);
  }
}

/* ---------- AI Detector: new check → latest result → previous checks ---------- */
const scanLevel = (kind, v) => {
  const l = CONFIG.scan.levels[kind];
  return v >= l.high ? 'High' : v < l.low ? 'Low' : 'Medium';
};
// Filled 16px circle icons for the table chips (Figma 181:1969): tick for Low, "!" for High, "i" for Medium
const LVL_ICONS = {
  low: '<svg class="lvl-ico" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.5"/><path d="m6.6 10.2 2.3 2.3 4.6-4.8" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  high: '<svg class="lvl-ico" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.5"/><path d="M10 5.8v5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><circle cx="10" cy="13.9" r="1.1" fill="#fff"/></svg>',
  medium: '<svg class="lvl-ico" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.5"/><path d="M10 9v5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><circle cx="10" cy="6.2" r="1.1" fill="#fff"/></svg>',
};

// Turnitin hides AI scores of 1–19% behind "*%": it still counts as Low
const scanValue = (scan, kind) => {
  const v = kind === 'ai' ? scan.ai : scan.sim;
  if (v != null) return v;
  return kind === 'ai' && scan.aiDisplay === '*%' ? 10 : null;
};
// Only "*%" (1–19% AI) needs separate highlights: at 0% there is nothing to show,
// and above 20% the AI report itself already marks the AI parts
const canSeeAiParts = (scan) => scan.hasHl || scan.aiDisplay === '*%';
const scanDisplay = (scan, kind) => {
  const v = kind === 'ai' ? scan.ai : scan.sim, d = kind === 'ai' ? scan.aiDisplay : scan.simDisplay;
  return v != null ? `${v}%` : d || '—';
};
const levelPill = (kind, scan, withValue) => {
  const v = scanValue(scan, kind);
  if (v == null) return `<span class="lvl lvl-medium">${withValue ? '— ' : ''}Not available</span>`;
  const lvl = scanLevel(kind, v).toLowerCase();
  return `<span class="lvl lvl-${lvl}">${withValue ? LVL_ICONS[lvl] : ''}${withValue ? esc(scanDisplay(scan, kind)) + ' ' : ''}${scanLevel(kind, v)}</span>`;
};

function fmtDateTime(iso) {
  const d = new Date(iso), time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return d.toDateString() === new Date().toDateString()
    ? `Today, ${time}` : `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}, ${time}`;
}

/* Checks come from /api/turnitin/reports. The checked text is kept in this browser
   so "Humanize this text" can send it on. */
const REPORT_STATUS = { queued: 'checking', running: 'checking', processing: 'checking', completed: 'done', failed: 'failed' };
const scanTexts = store.get('scan-texts', {});
function rememberScanText(id, text) {
  if (!id || !text) return;
  scanTexts[id] = text.slice(0, 200000);
  const ids = Object.keys(scanTexts);
  if (ids.length > 20) delete scanTexts[ids[0]];
  store.set('scan-texts', scanTexts);
}
const pctOrNull = (v) => (v == null || v === '' || Number.isNaN(Number(v)) ? null : Math.round(Number(v)));
function reportToScan(r) {
  return {
    id: r.id, file: r.filename, status: REPORT_STATUS[r.status] || 'checking',
    date: r.createdAt || new Date().toISOString(),
    ai: pctOrNull(r.aiScore), sim: pctOrNull(r.similarity),
    aiDisplay: r.aiScoreDisplay, simDisplay: r.similarityDisplay,
    hasAi: !!r.hasAiReport, hasSim: !!r.hasSimilarityReport, hasHl: !!r.hasHighlightsReport,
    hlStatus: r.highlightsStatus || '', error: r.errorMessage || '',
    official: r.provider === 'turnitin',
  };
}
function upsertScan(report) {
  const next = reportToScan(report), prev = findScan(next.id);
  if (prev) Object.assign(prev, next, { wantHl: prev.wantHl }); else state.scans.unshift(next);
  return prev || next;
}

const scanList = () => (state.signedIn ? state.scans : []);
const findScan = (id) => state.scans.find(s => s.id === id);
// Only the check started (or opened from Previous checks) in this visit; otherwise the empty state
function currentScan() {
  return scanList().find(s => s.id === state.scanCurrent) || null;
}

async function loadScans() {
  if (!state.signedIn) return;
  try {
    const data = await API.turnitin.list();
    const known = new Map(state.scans.map(s => [s.id, s]));
    state.scans = (data.reports || []).map(r => Object.assign(known.get(r.id) || {}, reportToScan(r)));
    state.scansLoaded = true;
    scheduleScanPoll();
    if (currentRoute() === 'turnitin' && !tour.name) rerenderScan();
  } catch (err) {
    if (err.code === 'AUTH_REQUIRED') onSignedOut();
  }
}

// Keep polling while a check runs, its reports are still downloading, or highlights are on the way
const SCAN_POLL_MS = 3000;
const SCAN_REPORT_WAIT_MS = 5 * 60000;
let scanPollTimer = null;
function scanPending(s) {
  if (s.status === 'checking') return true;
  if (s.hlStatus === 'queued' || s.hlStatus === 'running') return true;
  const recent = Date.now() - Date.parse(s.date) < SCAN_REPORT_WAIT_MS;
  return s.status === 'done' && !s.official && recent && (!s.hasSim || !s.hasAi);
}
function scheduleScanPoll() {
  clearTimeout(scanPollTimer);
  if (!state.scans.some(scanPending)) return;
  scanPollTimer = setTimeout(pollScans, SCAN_POLL_MS);
}
async function pollScans() {
  const pending = state.scans.filter(scanPending);
  await Promise.all(pending.map(async (s) => {
    try {
      const before = s.status, hadHl = s.hasHl;
      const scan = upsertScan((await API.turnitin.get(s.id)).report);
      if (before === 'checking' && scan.status !== 'checking') completeScan(scan);
      if (!hadHl && scan.hasHl && scan.wantHl) { scan.wantHl = false; downloadReport(scan, 'highlights'); }
      if (scan.hlStatus === 'failed' && scan.wantHl) { scan.wantHl = false; toast('Couldn’t get the AI parts for this check. Nothing was charged.'); }
    } catch (err) {
      if (err.status === 404) state.scans = state.scans.filter(x => x.id !== s.id);
    }
  }));
  if (currentRoute() === 'turnitin' && !tour.name && !state.scanMenu) rerenderScan();
  scheduleScanPoll();
}

function renderScan() {
  const item = ITEMS.turnitin, t = toolState('turnitin'), S = CONFIG.scan;
  const drop = t.file
    ? `<div class="scan-drop has-file" id="scan-drop">
         ${icon('file')}
         <span class="scan-drop-text"><strong>${esc(t.file.name)}</strong><span class="small muted">${fmtSize(t.file.size)} · ready to check</span></span>
         <span class="scan-file-actions">
           <button class="btn btn-sm" data-act="scan-upload">Replace file</button>
           <button class="btn btn-sm btn-ghost" data-act="scan-remove-file" aria-label="Remove ${esc(t.file.name)}">Remove</button>
         </span>
       </div>`
    : `<button type="button" class="scan-drop" id="scan-drop" data-act="scan-upload">
         ${icon('upload')}
         <span class="scan-drop-text"><strong>Drop your document here or <span class="link-like">browse</span></strong>
         <span class="small muted">${esc(S.formats)}, up to ${esc(S.maxFileSizeMb)} MB</span></span>
       </button>`;
  const runBtn = state.signedIn
    ? `<button class="btn btn-primary" data-act="scan-run" id="scan-run" ${t.file && !t.submitting ? '' : 'disabled'} ${t.file ? '' : 'title="Upload a document first"'}>${t.submitting ? 'Uploading…' : 'Check document'}</button>`
    : `<button class="btn btn-primary" data-act="signup">Sign up to check</button>`;
  const quick = state.detMode === 'quick';
  store.set('det-mode', state.detMode);   // the page reopens on the detector used last
  return `<div class="page">
    ${pageHead(item, '', quick ? '' : `<button class="btn btn-sm" data-act="start-tour" data-tour-name="scan">${icon('help')} Take the tour</button>`)}
    ${detSwitchHtml()}
    ${quick ? quickDetHtml() : `
    ${t.note ? `<p class="note">${esc(t.note)}</p>` : ''}
    <section class="card scan-upload" aria-label="New check">
      ${drop}
      <input type="file" id="scan-file" accept=".docx,.doc,.pdf,.txt" hidden>
      <div class="scan-run" id="scan-run-area">
        <span class="muted">Cost: <b>${esc(S.price)}</b></span>
        ${runBtn}
      </div>
    </section>
    <section class="card scan-result" id="scan-latest" aria-live="polite" aria-labelledby="scan-result-h">${scanResultHtml(currentScan())}</section>
    ${state.signedIn ? scanHistoryHtml() : ''}`}
  </div>`;
}

/* ---------- AI Detector: our own detector (default) and the Turnitin report, one switch on top ---------- */
function detSwitchHtml() {
  const D = CONFIG.detector, opt = (mode, ic) => {
    const o = D.switch[mode], on = state.detMode === mode;
    return `<button role="tab" aria-selected="${on}" tabindex="${on ? 0 : -1}" data-act="det-mode" data-v="${mode}">
      <span class="det-sw-ic" aria-hidden="true">${icon(ic)}</span>
      <span class="det-sw-text"><b>${esc(o.title)}</b><small>${esc(o.sub)}</small></span></button>`;
  };
  return `<div class="det-switch" role="tablist" aria-label="Detector">${opt('quick', 'flash')}${opt('turnitin', 'shield')}</div>`;
}

function quickDetHtml() {
  // Text only: files are checked by the Turnitin report
  const q = state.qd, D = CONFIG.detector;
  return `${q.note ? `<p class="note">${esc(q.note)}</p>` : ''}
    <section class="card qd" aria-label="${esc(D.switch.quick.title)}">
      <div class="qd-input">
        <div class="qd-label-row"><label class="qd-label" for="qd-text">Your text</label>
          ${qdMarked() ? '<span class="qd-legend" id="qd-legend"><span><i class="lv-ai"></i>Looks AI</span><span><i></i>Looks human</span></span>' : ''}</div>
        <div class="qd-field">
          <div class="qd-backdrop" id="qd-backdrop" aria-hidden="true">${qdBackdropHtml()}</div>
          <textarea class="input qd-text" id="qd-text" placeholder="Paste your essay, report or any text (at least ${D.minWords} words)…">${esc(q.text)}</textarea>
        </div>
        <div class="tool-bar">
          <span class="tool-meta"><span class="counter" id="qd-count" aria-live="polite">${qdCountText()}</span><span class="cost">Cost: <span class="free">Free</span></span></span>
          <span class="spacer"></span>
          <button class="btn" data-act="qd-clear">Clear</button>
          <button class="btn btn-primary" data-act="qd-run" id="qd-run" ${qdReady() ? '' : 'disabled'}>${icon('scan')} Detect AI</button>
        </div>
      </div>
      <div class="qd-result" id="qd-result" aria-live="polite">${qdResultHtml()}</div>
    </section>`;
}

const qdWords = () => countWords(state.qd.text);
const qdMaxWords = () => state.signedIn ? CONFIG.detector.maxWords : CONFIG.detector.guestMaxWords;
const qdReady = () => { const w = qdWords(); return w >= CONFIG.detector.minWords && w <= qdMaxWords() && state.qd.status !== 'loading'; };

function qdCountText() {
  const D = CONFIG.detector, w = qdWords(), max = qdMaxWords();
  if (w && w < D.minWords) return `${fmtNum(w)} words · add ${D.minWords - w} more`;
  if (w > max && !state.signedIn) return `${fmtNum(w)} / ${fmtNum(max)} words · sign up to check up to ${fmtNum(D.maxWords)}`;
  return `${fmtNum(w)} / ${fmtNum(max)} words`;
}

function qdResultHtml() {
  const q = state.qd, S = CONFIG.scan;
  if (q.status === 'loading') return `<div class="qd-gauge is-loading" aria-hidden="true"></div>
    <h2 class="qd-verdict" id="qd-result-h" tabindex="-1">Analyzing your text…</h2><p class="muted">This takes a few seconds.</p>`;
  if (q.status === 'error') return `<div class="qd-gauge is-empty" aria-hidden="true"><b>—%</b></div>
    <h2 class="qd-verdict" id="qd-result-h" tabindex="-1">Couldn’t check the text</h2>
    <p class="muted qd-sub" role="alert">${esc(q.error)}</p>`;
  if (q.status !== 'done') return `<div class="qd-gauge is-empty" aria-hidden="true"><b>—%</b></div>
    <h2 class="qd-verdict" id="qd-result-h" tabindex="-1">Your AI score appears here</h2>
    <ul class="qd-scale"><li><i class="lv-low"></i>Under ${S.levels.ai.low}% · looks human</li><li><i class="lv-medium"></i>${S.levels.ai.low}–${S.levels.ai.high - 1}% · some AI</li><li><i class="lv-high"></i>${S.levels.ai.high}%+ · likely AI</li></ul>`;
  const r = q.result, lv = scanLevel('ai', r.ai).toLowerCase();
  const scored = r.sents.filter(x => x.ai_prob != null), flagged = scored.filter(x => x.flagged).length;
  return `<div class="qd-gauge lv-${lv}" data-v="${r.ai}" style="--v:${q.animate ? 0 : r.ai};--vi:${q.animate ? 0 : r.ai}"><span class="visually-hidden">${r.ai}% AI</span><b aria-hidden="true"></b><small aria-hidden="true">AI</small></div>
    <h2 class="qd-verdict" id="qd-result-h" tabindex="-1">${esc(S.verdicts[scanLevel('ai', r.ai)].title)}</h2>
    <p class="muted qd-sub">${r.ai}% of your text looks AI-generated${flagged ? ` · ${flagged} of ${scored.length} sentences flagged` : ''}.${q.left != null ? ` ${q.left} free check${q.left === 1 ? '' : 's'} left today.` : ''}</p>
    <div class="qd-split" aria-hidden="true"><span class="lv-${lv}" style="width:${r.ai}%"></span></div>
    <div class="qd-split-legend"><span>AI ${r.ai}%</span><span>Human ${100 - r.ai}%</span></div>
    <div class="qd-actions">
      ${r.ai >= S.levels.ai.low ? `<button class="btn btn-primary" data-act="qd-humanize">${icon('sparkles')} Humanize this text</button>` : ''}
      <button class="btn" data-act="qd-turnitin">${icon('shield')} Get Turnitin report</button>
    </div>`;
}

// AI sentences are highlighted right in the text box: a layer behind the transparent textarea carries the same text with marks.
// The marks show only while the text is exactly the one that was checked.
const qdMarked = () => state.qd.status === 'done' && state.qd.result?.text === state.qd.text;

function qdBackdropHtml() {
  if (!qdMarked()) return '';
  // Server offsets count Unicode code points, so slice the text the same way
  const r = state.qd.result, chars = Array.from(r.text), part = (a, b) => esc(chars.slice(a, b).join(''));
  let pos = 0, html = '';
  for (const s of r.sents) {
    if (s.start < pos) continue;
    html += part(pos, s.start) + (s.flagged ? `<mark>${part(s.start, s.end)}</mark>` : part(s.start, s.end));
    pos = s.end;
  }
  return html + part(pos) + '\n';
}

function bindQuickDet() {
  const q = state.qd, ta = $('#qd-text');
  const sync = () => { $('#qd-count').textContent = qdCountText(); $('#qd-run').disabled = !qdReady(); };
  const back = $('#qd-backdrop');
  ta.addEventListener('input', () => {
    q.text = ta.value; sync();
    if (back.firstChild && !qdMarked()) { back.textContent = ''; $('#qd-legend')?.remove(); }   // edited: the marks no longer match
  });
  ta.addEventListener('scroll', () => { back.scrollTop = ta.scrollTop; });
  // Count the score up from 0 once, right after a check finishes
  const g = $('.qd-gauge[data-v]');
  if (g && q.animate) { q.animate = false; requestAnimationFrame(() => requestAnimationFrame(() => { g.style.setProperty('--v', g.dataset.v); g.style.setProperty('--vi', g.dataset.v); })); }
  if (q.autoRun) { q.autoRun = false; if (qdReady()) runQuickDet(); }
}

async function runQuickDet() {
  const q = state.qd;
  if (!qdReady()) return;
  const text = q.text;
  Object.assign(q, { status: 'loading', result: null, error: '', note: '' });
  rerenderScan('#qd-result-h');
  const show = () => { if (currentRoute() === 'turnitin' && state.detMode === 'quick') rerenderScan('#qd-result-h'); };
  let data;
  try {
    data = await API.detectFree(text);
  } catch (err) {
    const info = apiErrorInfo(err, { intent: 'turnitin' });
    Object.assign(q, { status: 'error', error: info.message || 'Something went wrong. Try again.' });
    show();
    return;
  }
  Object.assign(q, {
    status: 'done', result: { ai: data.ai_percent, sents: data.sentences || [], text },
    left: typeof data.checks_left === 'number' ? data.checks_left : null,
    animate: !matchMedia('(prefers-reduced-motion: reduce)').matches,
  });
  addDoc(text, 'turnitin', { ai: data.ai_percent, text });
  show();
}

function detAction(act, el) {
  const q = state.qd;
  switch (act) {
    case 'det-mode':
      if (tour.name) endTour();
      state.detMode = el.dataset.v;
      rerenderScan(`[data-act="det-mode"][data-v="${state.detMode}"]`);
      break;
    case 'qd-clear': Object.assign(q, { text: '', status: 'idle', result: null, error: '', note: '' }); rerenderScan('#qd-text'); break;
    case 'qd-run': runQuickDet(); break;
    case 'qd-humanize':
      Object.assign(toolState('humanizer'), { mode: 'paste', text: q.text, fileName: '', status: 'idle', result: null, note: `Text from ${CONFIG.detector.switch.quick.title}.` });
      go('humanizer');
      break;
    case 'qd-turnitin': {
      const blob = new File([q.text], 'Your text.txt', { type: 'text/plain' });
      Object.assign(toolState('turnitin'), { file: { name: blob.name, size: blob.size, blob, text: q.text },
        note: 'Your text is attached. Press Check document for the official Turnitin report.' });
      state.detMode = 'turnitin';
      rerenderScan('#scan-run');
      window.scrollTo(0, 0);
      break;
    }
  }
}

function scanResultHtml(scan) {
  const S = CONFIG.scan;
  if (!scan) return `<div class="scan-empty">
      <span class="scan-empty-icon" aria-hidden="true">${icon('scan')}</span>
      <h2 id="scan-result-h" tabindex="-1">Your result will appear here</h2>
      <p class="muted">${state.signedIn ? 'Upload a document and press Check document.' : 'Sign up to check documents.'}
        You get a clear verdict, AI and similarity scores, and both reports to download.</p>
      <div class="scan-empty-preview" aria-hidden="true">
        <span class="scan-empty-box"><span>AI score</span><b>—%</b><i></i></span>
        <span class="scan-empty-box"><span>Similarity</span><b>—%</b><i></i></span>
      </div>
    </div>`;
  const checking = scan.status === 'checking', failed = scan.status === 'failed';
  const head = `<div class="res-file">
      <span class="doc-icon">${icon('file')}</span>
      <div class="res-file-main"><b>${esc(scan.file)}</b>
        <span class="small muted">${checking ? 'Started' : 'Checked'} ${fmtDateTime(scan.date).replace('Today', 'today')}</span></div>
      <span class="status ${checking ? 'status-checking' : 'status-done'}">${checking ? 'Checking' : failed ? 'Failed' : 'Completed'}</span>
    </div>`;
  if (checking) return `${head}
    <h2 class="verdict" id="scan-result-h" tabindex="-1">Checking your document…</h2>
    <div class="loading"><span class="spinner" aria-hidden="true"></span>${esc(S.checkingNote)}. You can leave this page, the result will be saved.</div>`;
  if (failed) return `${head}
    <h2 class="verdict" id="scan-result-h" tabindex="-1">The check didn’t finish</h2>
    <p class="muted" style="margin:0">${esc(scan.error || S.failedNote)} Your credits were refunded.</p>
    <div class="scan-actions"><button class="btn btn-primary" data-act="scan-retry" data-id="${scan.id}">Try again</button></div>`;

  const aiValue = scanValue(scan, 'ai');
  const v = aiValue == null ? { title: 'AI score is not available', text: 'This check returned only the similarity score.' } : S.verdicts[scanLevel('ai', aiValue)];
  const simValue = scanValue(scan, 'similarity');
  const simHigh = simValue != null && scanLevel('similarity', simValue) === 'High';
  const score = (kind, label, report) => {
    const value = scanValue(scan, kind), ready = kind === 'ai' ? scan.hasAi : scan.hasSim;
    const lv = value == null ? 'medium' : scanLevel(kind, value).toLowerCase();
    return `<div class="score">
      <div class="score-top"><span>${label}</span>${levelPill(kind, scan)}</div>
      <div class="score-val">${esc(scanDisplay(scan, kind))}</div>
      <div class="meter-bar"><span class="bar-${lv}" style="width:${Math.max(value || 0, 2)}%"></span></div>
      <button class="btn btn-block" data-act="scan-download" data-kind="${report}" data-id="${scan.id}" ${ready ? '' : 'disabled'}>
        ${icon('download')} ${ready ? `Download ${report} report` : 'Report is on the way…'}</button>
    </div>`;
  };
  const canHighlight = canSeeAiParts(scan);
  const hlBusy = scan.hlStatus === 'queued' || scan.hlStatus === 'running';
  return `${head}
    <h2 class="verdict" id="scan-result-h" tabindex="-1">${esc(v.title)}</h2>
    <p class="muted" style="margin:0">${esc(v.text)}${simHigh ? ' ' + esc(S.highSimilarityNote) : ''}</p>
    <div class="scores">${score('ai', 'AI score', 'AI')}${score('similarity', 'Similarity', 'similarity')}</div>
    <div class="scan-actions">
      ${canHighlight ? `<button class="btn btn-primary" data-act="scan-highlights" data-id="${scan.id}" ${hlBusy ? 'disabled' : ''}>
        ${hlBusy ? 'Finding AI parts…' : 'See which parts look AI'} <span class="badge badge-inverse">Free</span></button>` : ''}
      <button class="btn" data-act="scan-humanize" data-id="${scan.id}">${icon('sparkles')} Humanize this text</button>
    </div>
    ${canHighlight ? `<p class="small muted" style="margin:12px 0 0">${esc(S.lowAiHighlightsNote)}</p>` : ''}`;
}

function scanHistoryHtml() {
  const S = CONFIG.scan, list = scanList(), cur = currentScan();
  const dl = (s, kind) => {
    const ready = kind === 'AI' ? s.hasAi : s.hasSim;
    return `<button class="icon-btn" data-act="scan-download" data-kind="${kind}" data-id="${s.id}" ${ready ? '' : 'disabled'} aria-label="Download ${kind} report for ${esc(s.file)}">${icon('download')}</button>`;
  };
  const more = (s) => `<button class="icon-btn" data-act="scan-menu" data-id="${s.id}" aria-haspopup="menu" aria-expanded="${state.scanMenu === s.id}" aria-label="More actions for ${esc(s.file)}">${icon('more')}</button>`;
  const row = (s) => {
    const file = `<td><button class="file-btn" data-act="scan-show" data-id="${s.id}" title="${esc(s.file)}">${esc(s.file)}</button></td>`;
    const date = `<td class="muted">${fmtDateTime(s.date)}</td>`;
    if (s.status === 'checking') return `<tr>${file}<td class="muted">Checking…</td><td class="muted">Checking…</td>${date}
      <td><div class="row-actions"><span class="muted">${esc(S.checkingNote)}</span></div></td></tr>`;
    if (s.status === 'failed') return `<tr>${file}<td colspan="2" class="fail">${esc(S.failedNote)}</td>${date}
      <td><div class="row-actions"><button class="btn btn-sm" data-act="scan-retry" data-id="${s.id}">Try again</button>${more(s)}</div></td></tr>`;
    return `<tr class="${cur && cur.id === s.id ? 'is-current' : ''}">${file}
      <td><span class="cell">${levelPill('ai', s, true)}${dl(s, 'AI')}</span></td>
      <td><span class="cell">${levelPill('similarity', s, true)}${dl(s, 'similarity')}</span></td>
      ${date}
      <td><div class="row-actions">
        ${canSeeAiParts(s) ? `<button class="btn btn-sm btn-outline-accent" data-act="scan-highlights" data-id="${s.id}">See AI parts <span class="badge">Free</span></button>` : ''}
        ${more(s)}</div></td></tr>`;
  };
  const menuScan = state.scanMenu && findScan(state.scanMenu);
  return `<section class="section" id="scan-history" aria-labelledby="hist-h">
    <h2 id="hist-h" tabindex="-1">Previous checks</h2>
    ${list.length ? `<div class="table-wrap"><table class="hist">
        <thead><tr><th scope="col">File</th><th scope="col">AI score</th><th scope="col">Similarity</th><th scope="col">Checked</th><th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead>
        <tbody>${list.map(row).join('')}</tbody></table></div>`
      : `<div class="card empty">${state.scansLoaded ? 'Your checks will appear here, with both reports to download.' : 'Loading your checks…'}</div>`}
    ${menuScan ? `<div class="menu" role="menu" id="scan-menu" aria-label="Actions for ${esc(menuScan.file)}">
        ${menuScan.status === 'done' ? `<button role="menuitem" data-act="scan-show" data-id="${menuScan.id}">Show result</button>` : ''}
        <button role="menuitem" data-act="scan-delete" data-id="${menuScan.id}">Delete check</button></div>` : ''}
  </section>`;
}

function rerenderScan(focusSel) {
  $('#main').innerHTML = renderScan();
  bindScan();
  if (focusSel) $(focusSel)?.focus({ preventScroll: true });
}

const SCAN_FILE_RE = /\.(docx?|pdf|txt)$/i;
const SCAN_MAX_BYTES = 16 * 1024 * 1024;

function bindScan() {
  if (state.detMode === 'quick') return bindQuickDet();
  const t = toolState('turnitin'), input = $('#scan-file'), zone = $('.scan-upload');
  const take = (file) => {
    if (!file) return;
    if (!SCAN_FILE_RE.test(file.name)) { toast('Please choose a .docx, .pdf or .txt file'); return; }
    if (file.size > SCAN_MAX_BYTES) { toast(`The file is larger than ${CONFIG.scan.maxFileSizeMb} MB`); return; }
    t.file = { name: file.name, size: file.size, blob: file, text: null };
    t.note = '';
    API.extractText(file).then(text => { if (t.file?.blob === file) t.file.text = text; }).catch(() => {});
    rerenderScan('#scan-run');
  };
  input.addEventListener('change', () => take(input.files[0]));
  zone.addEventListener('dragover', (e) => { e.preventDefault(); $('#scan-drop').classList.add('drag'); });
  zone.addEventListener('dragleave', (e) => { if (!zone.contains(e.relatedTarget)) $('#scan-drop').classList.remove('drag'); });
  zone.addEventListener('drop', (e) => { e.preventDefault(); take(e.dataTransfer.files[0]); });
  // The "⋯" menu is positioned next to its button, outside the scrolling table
  const menu = $('#scan-menu');
  if (menu) {
    const r = $(`[data-act="scan-menu"][data-id="${state.scanMenu}"]`).getBoundingClientRect();
    menu.style.top = Math.min(r.bottom + 4, innerHeight - menu.offsetHeight - 8) + 'px';
    menu.style.left = Math.max(8, r.right - menu.offsetWidth) + 'px';
  }
}

function closeScanMenu(focusTrigger) {
  const id = state.scanMenu;
  if (!id) return;
  state.scanMenu = null;
  rerenderScan(focusTrigger ? `[data-act="scan-menu"][data-id="${id}"]` : null);
}
window.addEventListener('scroll', () => { if (state.scanMenu) closeScanMenu(false); }, { passive: true });

async function runScan() {
  const t = toolState('turnitin');
  if (!t.file?.blob || t.submitting) return;
  t.submitting = true;
  rerenderScan();
  const { blob, text } = t.file;
  try {
    const data = await API.turnitin.check(blob);
    if (typeof data.balance === 'number') state.balance = data.balance;
    const scan = upsertScan({ id: data.submission_id, filename: data.filename || blob.name, status: data.status || 'queued', createdAt: new Date().toISOString(), provider: data.provider });
    rememberScanText(scan.id, text);
    state.scanCurrent = scan.id;
    t.file = null; t.note = '';
    renderHeader();
    loadCredits();
    scheduleScanPoll();
  } catch (err) {
    const e = apiErrorInfo(err, { intent: 'turnitin' });
    if (!e.handled) t.note = e.message;
  } finally {
    t.submitting = false;
  }
  if (currentRoute() === 'turnitin') rerenderScan(state.scanCurrent ? '#scan-result-h' : '#scan-run');
}

// A check just finished: History on Home, balance (refund on failure)
function completeScan(scan) {
  if (scan.status === 'done') {
    state.docs.unshift({ id: 'd' + Date.now(), title: scan.file, tool: 'turnitin', date: todayIso(), ai: scan.ai, scanId: scan.id, text: scanTexts[scan.id] || '' });
    saveDocs();
  }
  loadCredits();
}

function downloadReport(scan, kind) {
  const a = Object.assign(document.createElement('a'), { href: API.turnitin.reportUrl(scan.id, kind), download: '' });
  document.body.append(a); a.click(); a.remove();
}

async function requestHighlights(scan) {
  if (scan.hasHl) return downloadReport(scan, 'highlights');
  try {
    const data = await API.turnitin.highlights(scan.id);
    if (data.viewer_url) window.open(data.viewer_url, '_blank', 'noopener');
    if (data.report) upsertScan(data.report); else scan.hlStatus = data.highlights_status || 'queued';
    if (scan.hasHl) { downloadReport(scan, 'highlights'); return; }
    scan.wantHl = true;
    toast('Finding the AI parts. The PDF downloads when it’s ready.');
    scheduleScanPoll();
  } catch (err) {
    toast(apiErrorInfo(err).message);
  }
  if (currentRoute() === 'turnitin') rerenderScan();
}

async function scanTextFor(scan) {
  if (scanTexts[scan.id]) return scanTexts[scan.id];
  const doc = state.docs.find(d => d.scanId === scan.id && d.text);
  return doc ? doc.text : '';
}

function scanAction(act, el) {
  const scan = el.dataset.id && findScan(el.dataset.id);
  switch (act) {
    case 'scan-upload': $('#scan-file').click(); break;
    case 'scan-remove-file': Object.assign(toolState('turnitin'), { file: null, note: '' }); rerenderScan('#scan-drop'); break;
    case 'scan-run': runScan(); break;
    case 'scan-show':
      state.scanCurrent = scan.id; state.scanMenu = null;
      rerenderScan();
      $('#scan-latest').scrollIntoView({ behavior: 'smooth', block: 'start' });
      $('#scan-result-h').focus({ preventScroll: true });
      break;
    case 'scan-menu':
      state.scanMenu = state.scanMenu === scan.id ? null : scan.id;
      rerenderScan(state.scanMenu ? '#scan-menu [role=menuitem]' : `[data-act="scan-menu"][data-id="${scan.id}"]`);
      break;
    case 'scan-delete':
      state.scanMenu = null;
      rerenderScan();
      askConfirm({
        title: 'Delete check?', okLabel: 'Delete',
        text: `“${scan.file}” and its reports will be removed. This can’t be undone.`,
        opener: $(`[data-act="scan-menu"][data-id="${scan.id}"]`),
        onOk: () => {
          API.turnitin.remove(scan.id).then(() => {
            state.scans = state.scans.filter(s => s.id !== scan.id);
            if (state.scanCurrent === scan.id) state.scanCurrent = null;
            if (currentRoute() === 'turnitin') rerenderScan('#hist-h');
            toast(`Deleted “${scan.file}”`);
          }).catch(err => toast(apiErrorInfo(err).message));
          return $('#hist-h');
        },
      });
      break;
    case 'scan-retry': {
      // A failed check was refunded: run the same text again if we still have it, otherwise ask for the file
      const text = scanTexts[scan.id];
      const t = toolState('turnitin');
      if (text) {
        const name = /\.txt$/i.test(scan.file) ? scan.file : scan.file.replace(/\.[^.]+$/, '') + '.txt';
        const blob = new File([text], name, { type: 'text/plain' });
        t.file = { name, size: blob.size, blob, text };
        runScan();
      } else {
        t.note = `Upload “${scan.file}” again to retry the check.`;
        rerenderScan('#scan-drop');
      }
      break;
    }
    case 'scan-download': downloadReport(scan, el.dataset.kind === 'AI' ? 'ai' : 'similarity'); break;
    case 'scan-highlights': requestHighlights(scan); break;
    case 'scan-humanize':
      scanTextFor(scan).then(text => {
        Object.assign(toolState('humanizer'), { mode: 'paste', text, fileName: '', status: 'idle', result: null,
          note: text ? `Text from “${scan.file}”.` : `Upload “${scan.file}” or paste its text to humanize it.` });
        go('humanizer');
      });
      break;
  }
}

/* =========================================================
   Guided tour — spotlight on a block + popover with steps.
   Steps live in CONFIG.tours; steps whose target is hidden are skipped.
   ========================================================= */
const tour = { name: null, steps: [], i: 0, opener: null, loadedSample: false };

// How each tool gets sample input when its tour starts with an empty input
const TOUR_SAMPLES = {
  turnitin: {
    empty: (t) => !t.file,
    load: (t) => {
      const blob = new File([CONFIG.scan.sampleText], 'Sample_essay.txt', { type: 'text/plain' });
      return Object.assign(t, { file: { name: blob.name, size: blob.size, blob, text: CONFIG.scan.sampleText }, note: '' });
    },
  },
  humanizer: {
    empty: (t) => !t.text.trim() && t.status !== 'loading',
    load: (t) => Object.assign(t, { mode: 'paste', text: CONFIG.scan.sampleText, fileName: '', status: 'idle', result: null, note: 'Sample text loaded for the tour.' }),
  },
};

function startTour(name) {
  const cfg = CONFIG.tours[name], toolId = cfg.route, t = toolState(toolId);
  tour.loadedSample = false;
  const sample = TOUR_SAMPLES[toolId];
  if (sample && sample.empty(t)) {
    sample.load(t);
    $('#main').innerHTML = PAGES[toolId]();
    bindPage(toolId);
    tour.loadedSample = true;
  }
  const visible = (sel) => { const el = $(sel); return el && el.offsetParent !== null && !el.closest('[inert]'); };
  tour.steps = cfg.steps.filter(s => visible(s.target));
  if (!tour.steps.length || $('dialog[open]')) return;
  tour.name = name; tour.i = 0;
  tour.opener = document.activeElement;
  hideTip();
  $('#tour').hidden = false;
  showTourStep();
}

function showTourStep() {
  const s = tour.steps[tour.i], n = tour.steps.length;
  const text = (!state.signedIn && s.textGuest) || (tour.loadedSample && s.textSample) || s.text;
  $('#tour-count').textContent = `${tour.i + 1} of ${n}`;
  $('#tour-title').textContent = s.title;
  $('#tour-text').textContent = text;
  $('[data-tour="back"]').hidden = tour.i === 0;
  $('[data-tour="next"]').textContent = tour.i === n - 1 ? 'Done' : 'Next';
  const target = $((!state.signedIn && s.targetGuest) || s.target);
  if (!target) { endTour(); return; }
  target.scrollIntoView({ block: 'center', behavior: 'instant' });
  positionTour(true);
  $('[data-tour="next"]').focus();
}

function positionTour(allowScroll) {
  if (!tour.name) return;
  const el = $(tour.steps[tour.i].target), spot = $('#tour-spot'), pop = $('#tour-pop');
  if (!el) return;
  const pad = 8, gap = 12, edge = 16;
  let r = el.getBoundingClientRect();
  // Tall block: scroll it to the top so the popover fits underneath
  if (allowScroll === true && r.bottom + pad + gap + pop.offsetHeight > innerHeight - edge && r.top - pad - gap - pop.offsetHeight < edge) {
    window.scrollBy(0, r.top - pad - edge);
    r = el.getBoundingClientRect();
  }
  Object.assign(spot.style, { left: r.left - pad + 'px', top: r.top - pad + 'px', width: r.width + pad * 2 + 'px', height: r.height + pad * 2 + 'px' });
  const w = pop.offsetWidth, h = pop.offsetHeight;
  let top = r.bottom + pad + gap;                                   // below the block…
  if (top + h > innerHeight - edge) top = r.top - pad - gap - h;    // …or above…
  let left = r.left - pad;
  if (top < edge) {                                                 // …or beside it
    top = Math.min(Math.max(edge, r.top), innerHeight - h - edge);
    if (r.right + pad + gap + w <= innerWidth - edge) left = r.right + pad + gap;
    else if (r.left - pad - gap - w >= edge) left = r.left - pad - gap - w;
    else top = innerHeight - h - edge;                              // no room anywhere: bottom of the screen
  }
  pop.style.top = Math.max(edge, top) + 'px';
  pop.style.left = Math.min(Math.max(edge, left), innerWidth - w - edge) + 'px';
}

function endTour() {
  if (!tour.name) return;
  store.set('tour-' + tour.name + '-seen', true);
  tour.name = null;
  $('#tour').hidden = true;
  const back = tour.opener && document.contains(tour.opener) && tour.opener !== document.body ? tour.opener : $('#main');
  back?.focus();
}

$('#tour').addEventListener('click', (e) => {
  const b = e.target.closest('[data-tour]');
  if (!b) return;
  const act = b.dataset.tour;
  if (act === 'skip') endTour();
  if (act === 'back') { tour.i--; showTourStep(); }
  if (act === 'next') { if (tour.i === tour.steps.length - 1) endTour(); else { tour.i++; showTourStep(); } }
});
$('#tour').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.stopPropagation(); endTour(); return; }
  if (e.key !== 'Tab') return;                                      // keep focus inside the popover
  const f = $$('#tour-pop button:not([hidden])');
  const i = f.indexOf(document.activeElement);
  if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
  else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
});
window.addEventListener('resize', positionTour);
window.addEventListener('scroll', positionTour, { passive: true });

/* ---------- Editor (Workspace): Word-like document + AI & Humanize panel ---------- */
// The document, its versions and comments are kept in this browser, one document per account
const edKey = () => 'editor-' + (BOOT.user ? BOOT.user.id : 'guest');
const ED_SAVED = ['title', 'html', 'zoom', 'checked', 'aiPercent', 'versions', 'comments'];
const ED_MAX_VERSIONS = 10;
const ED_VERSION_EVERY_MS = 10 * 60 * 1000;
const ED_MAX_HUMANIZE_WORDS = 5000;      // one humanizer run; larger selections would need several paid runs
const edCiteStyle = () => {
  const s = String(state.profile?.style || '');
  return CONFIG.editor.citeStyles.find(x => s.startsWith(x.split(' ')[0])) || CONFIG.editor.citeStyles[0];
};
const newEditor = (o = {}) => ({
  title: CONFIG.editor.sampleTitle, html: CONFIG.editor.sampleHtml, zoom: 1, tab: 'ai', checked: false, aiPercent: null,
  flagIdx: -1, busy: false, error: null, versions: [], comments: [], cmtQuote: '',
  cite: { style: edCiteStyle(), query: '', results: null, busy: false, error: '' }, ...o,
});
const edState = () => {
  if (state.editor) return state.editor;
  const saved = BOOT.user ? store.get(edKey(), null) : null;
  return (state.editor = newEditor(saved ? Object.fromEntries(ED_SAVED.filter(k => k in saved).map(k => [k, saved[k]])) : {}));
};
let edRange = null;          // last selection inside the document
let edCaret = null;          // last cursor position inside the document (citations go here)
let edSavedTimer = null;
const edUnwrap = (el) => el.replaceWith(...el.childNodes);
const fmtWhen = (ts) => new Date(ts).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

// False when the browser refuses to store it (quota): the oldest versions are dropped first
function edPersist() {
  const e = state.editor;
  if (!e || !state.signedIn) return true;
  const data = () => Object.fromEntries(ED_SAVED.map(k => [k, e[k]]));
  while (!store.set(edKey(), data())) {
    if (!e.versions.length) return false;
    e.versions.pop();
  }
  return true;
}

function edSnapshot(label, html) {
  const e = edState();
  const doc = $('#doc');
  html = html ?? (doc ? doc.innerHTML.replace(/ is-current/g, '') : e.html);
  if (e.versions[0]?.html === html) return;
  e.versions.unshift({ at: Date.now(), title: e.title, html, label });
  e.versions.length = Math.min(e.versions.length, ED_MAX_VERSIONS);
}

// Open another document in the editor; the current one stays in Version history
function edReplaceDoc(title, html, label) {
  const e = edState();
  edSnapshot(label);
  Object.assign(e, { title, html, checked: false, aiPercent: null, flagIdx: -1, error: null });
  edPersist();
  if (currentRoute() === 'workspace') render();
}

// Toolbar: [execCommand, label, content, tooltip line]
const ED_TOOLS = [
  ['undo', 'Undo', icon('undo'), 'Ctrl/⌘ + Z'], ['redo', 'Redo', icon('redo'), 'Ctrl/⌘ + Shift + Z'], '|', 'block', '|',
  ['bold', 'Bold', 'B', 'Ctrl/⌘ + B'], ['italic', 'Italic', '<i>I</i>', 'Ctrl/⌘ + I'], ['underline', 'Underline', '<u>U</u>', 'Ctrl/⌘ + U'],
  ['strikeThrough', 'Strikethrough', '<s>S</s>', ''], '|',
  ['superscript', 'Superscript', '<span>x<sup>2</sup></span>', 'Raise text, like x²'], ['subscript', 'Subscript', '<span>x<sub>2</sub></span>', 'Lower text, like H₂O'],
  ['removeFormat', 'Clear formatting', icon('clearFormat'), 'Remove bold, italic and other styles'], '|',
  ['justifyLeft', 'Align left', icon('alignLeft'), ''], ['justifyCenter', 'Align center', icon('alignCenter'), ''],
  ['justifyRight', 'Align right', icon('alignRight'), ''], ['justifyFull', 'Justify', icon('alignJustify'), ''], '|',
  ['insertUnorderedList', 'Bulleted list', icon('listBullet'), ''], ['insertOrderedList', 'Numbered list', icon('listNumber'), ''],
  ['outdent', 'Decrease indent', icon('outdent'), ''], ['indent', 'Increase indent', icon('indent'), ''],
];
const ED_TOGGLES = ['bold', 'italic', 'underline', 'strikeThrough', 'superscript', 'subscript'];

function renderEditor() {
  const e = edState(), E = CONFIG.editor;
  const tb = ED_TOOLS.map(t => {
    if (t === '|') return '<span class="tb-sep" aria-hidden="true"></span>';
    if (t === 'block') return `<label class="visually-hidden" for="ed-block">Text style</label>
      <select id="ed-block" class="select tb-select" data-tip-title="Text style" data-tip-desc="Normal text or a heading" data-tip-pos="bottom">
        ${E.blockStyles.map(b => `<option value="${b.tag}">${esc(b.label)}</option>`).join('')}</select>`;
    const [cmd, label, content, hint] = t;
    return `<button type="button" class="tb-btn" data-cmd="${cmd}" aria-label="${label}" data-tip-title="${label}" data-tip-desc="${esc(hint)}" data-tip-pos="bottom"
      ${ED_TOGGLES.includes(cmd) ? 'aria-pressed="false"' : ''}>${content}</button>`;
  }).join('');
  return `<div class="editor">
    <header class="ed-top">
      <div class="ed-title-wrap">
        <label class="visually-hidden" for="ed-title">Document title</label>
        <input id="ed-title" class="ed-title" value="${esc(e.title)}" autocomplete="off" title="${esc(e.title)}">
        <span class="small muted ed-saved" id="ed-saved" aria-live="polite">${state.signedIn ? 'All changes saved' : 'Sign up to save changes'}</span>
      </div>
      <div class="ed-top-actions">
        <button class="icon-btn" data-act="start-tour" data-tour-name="editor" aria-label="Take the tour" data-tip-title="Take the tour" data-tip-desc="4 quick steps" data-tip-pos="bottom">${icon('help')}</button>
        <button class="icon-btn" data-act="ed-versions" aria-haspopup="menu" aria-label="Version history" data-tip-title="Version history" data-tip-desc="See and restore earlier versions" data-tip-pos="bottom">${icon('history')}</button>
        <button class="btn btn-sm" data-act="ed-open" aria-haspopup="menu" data-tip-title="Open" data-tip-desc="Open a .docx, .pdf or .txt file, or start a blank document" data-tip-pos="bottom">${icon('upload')} Open</button>
        <input type="file" id="ed-file" accept=".docx,.pdf,.txt" hidden>
        <button class="btn btn-sm btn-primary" id="ed-export" data-act="ed-export" aria-haspopup="menu">${icon('download')} Export</button>
      </div>
    </header>
    <div class="ed-toolbar" role="toolbar" aria-label="Formatting" aria-controls="doc">${tb}</div>
    <div class="ed-body">
      <div class="ed-scroll" id="ed-scroll">
        <article class="doc-page" id="doc" contenteditable="true" spellcheck="true" role="textbox" aria-multiline="true"
          aria-label="Document text" style="zoom:${e.zoom}">${e.html}</article>
      </div>
      <aside class="ed-panel" aria-label="Assistant">
        <div class="ed-tabs" role="tablist" aria-label="Assistant tools">
          ${[['ai', 'AI & Humanize'], ['cite', 'Cite'], ['comments', 'Comments']].map(([k, l]) =>
            `<button role="tab" id="ed-tab-${k}" aria-controls="ed-panel-body" aria-selected="${e.tab === k}" tabindex="${e.tab === k ? 0 : -1}" data-act="ed-tab" data-tab="${k}">${l}</button>`).join('')}
        </div>
        <div id="ed-panel-body" role="tabpanel" aria-labelledby="ed-tab-${e.tab}" data-flags="-1">${edPanelHtml()}</div>
      </aside>
    </div>
    <footer class="ed-status" aria-label="Document status">
      <span id="st-words"></span><span id="st-chars"></span><span id="st-pages"></span>
      <span class="spacer"></span>
      <span class="ed-zoom" role="group" aria-label="Zoom">
        <button class="icon-btn" data-act="ed-zoom" data-step="-0.1" aria-label="Zoom out">${icon('minus')}</button>
        <output id="st-zoom" aria-live="polite">${Math.round(e.zoom * 100)}%</output>
        <button class="icon-btn" data-act="ed-zoom" data-step="0.1" aria-label="Zoom in">${icon('plus')}</button>
      </span>
    </footer>
  </div>`;
}

// One flagged sentence can cross bold/italic boundaries, so it may be several <mark>s sharing data-part;
// edFlags() returns the first mark of each part.
const edFlags = () => $$('#doc .ai-flag:not([data-cont])');
const edParts = (f) => $$(`#doc .ai-flag[data-part="${f.dataset.part}"]`);
const edPartText = (f) => edParts(f).map(m => m.textContent).join('');
function edPartRange(f, inner) {
  const pieces = edParts(f), last = pieces[pieces.length - 1], r = document.createRange();
  if (inner) { r.setStart(pieces[0], 0); r.setEnd(last, last.childNodes.length); } else { r.setStartBefore(pieces[0]); r.setEndAfter(last); }
  return r;
}
const edSuggs = () => $$('#doc .sugg');
const edHasSel = () => !!(edRange && !edRange.collapsed && edRange.toString().trim() && !edInSugg(edRange));
const edInSugg = (r) => !!(r.startContainer.parentElement?.closest('.sugg') || r.endContainer.parentElement?.closest('.sugg'));

function edPanelHtml() {
  const e = edState(), E = CONFIG.editor;
  if (e.tab === 'cite') {
    const c = e.cite;
    const list = !c.results ? ''
      : !c.results.length ? '<p class="small muted">No sources found. Try other words.</p>'
      : `<ul class="ed-cite-list">${c.results.map((r, i) => `<li class="ed-cite-item">
          <b>${esc(r.title || 'Untitled')}</b>
          <span class="small muted">${esc([(r.authors || []).slice(0, 3).join(', '), r.year, r.journal].filter(Boolean).join(' · '))}</span>
          <div class="ed-cite-actions">
            <button class="btn btn-sm" data-act="ed-cite-insert" data-i="${i}" data-tip-title="Insert at the cursor" data-tip-desc="${esc(E.citePrice)}" data-tip-pos="bottom">Insert ${esc(r.intext || '')}</button>
            <button class="btn btn-sm btn-ghost" data-act="ed-cite-ref" data-i="${i}" data-tip-title="Add to References" data-tip-desc="${esc(E.citePrice)}" data-tip-pos="bottom">Add reference</button>
          </div></li>`).join('')}</ul>`;
    return `<section class="ed-block"><h3>Cite</h3>
      <p class="muted small">Find a source, then insert an in-text citation at the cursor or add it to the reference list. Search is free; each insert costs ${esc(E.citePrice)}.</p>
      <form class="ed-cite-form" id="ed-cite-form">
        <label class="visually-hidden" for="ed-cite-style">Citation style</label>
        <select id="ed-cite-style" class="select">${E.citeStyles.map(s => `<option ${s === c.style ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select>
        <label class="visually-hidden" for="ed-cite-q">Search for a source</label>
        <input id="ed-cite-q" class="input field-input" type="search" placeholder="Title, author or topic" value="${esc(c.query)}" autocomplete="off">
        <button class="btn btn-block" type="submit" ${c.busy ? 'disabled' : ''}>${icon('search')} ${c.busy ? 'Searching…' : 'Search'}</button>
      </form>
      ${c.error ? `<p class="field-err" role="alert">${esc(c.error)}</p>` : ''}
      ${list}</section>`;
  }
  if (e.tab === 'comments') return `<section class="ed-block"><h3>Comments</h3>
    <p class="muted small">Notes for yourself, kept with this document in this browser. Select text first to quote it.</p>
    <blockquote class="ed-cmt-quote small" id="ed-cmt-quote" ${e.cmtQuote ? '' : 'hidden'}>${esc(e.cmtQuote.slice(0, 180))}</blockquote>
    <label class="visually-hidden" for="ed-cmt-text">Comment</label>
    <textarea id="ed-cmt-text" class="input field-input ed-cmt-text" rows="3" placeholder="Write a comment…"></textarea>
    <button class="btn btn-block" data-act="ed-cmt-add">Add comment</button>
    ${e.comments.length ? `<ul class="ed-cmt-list">${e.comments.map(c => `<li class="ed-cmt-item">
        ${c.quote ? `<button class="ed-cmt-q small" data-act="ed-cmt-find" data-id="${c.id}" data-tip-title="Show in the document" data-tip-desc="" data-tip-pos="bottom">“${esc(c.quote.slice(0, 120))}”</button>` : ''}
        <p>${esc(c.text)}</p>
        <div class="ed-cmt-meta"><span class="small muted">${esc(fmtWhen(c.at))}</span>
          <button class="btn btn-sm btn-ghost" data-act="ed-cmt-del" data-id="${c.id}">Delete</button></div></li>`).join('')}</ul>`
      : '<p class="small muted">No comments yet.</p>'}
    </section>`;

  const flags = edFlags(), suggs = edSuggs(), busy = e.busy;
  const flagWords = flags.reduce((n, f) => n + countWords(edPartText(f)), 0);
  const score = e.aiPercent != null ? `<p class="small" style="margin:0"><b>${esc(String(e.aiPercent))}% AI</b> in the last check</p>` : '';
  const err = e.error ? assignErrorHtml(e.error.message, e.error.action === 'topup'
    ? '<button class="btn btn-sm btn-primary" data-act="topup">Top up credits</button>' : '') : '';
  const result = flags.length
    ? `<div class="ed-result-row">
         <span><b>${flags.length} part${flags.length > 1 ? 's' : ''}</b> · ${flagWords} words</span>
         <span class="ed-nav">
           <button class="icon-btn" data-act="ed-flag" data-dir="-1" aria-label="Previous AI part" data-tip-title="Previous part" data-tip-desc="" data-tip-pos="bottom">${icon('chevL')}</button>
           <span id="ed-flag-pos">${e.flagIdx >= 0 ? e.flagIdx + 1 : '–'} / ${flags.length}</span>
           <button class="icon-btn" data-act="ed-flag" data-dir="1" aria-label="Next AI part" data-tip-title="Next part" data-tip-desc="" data-tip-pos="bottom">${icon('chevR')}</button>
         </span>
       </div>`
    : `<p class="small muted">${e.checked ? 'No AI-looking parts left.' : 'Run a check to find parts that look AI-written.'}</p>`;
  return `
    <section class="ed-block" id="ed-check">
      <h3>1. Check</h3>
      <p class="small muted">Find parts of the document that look AI-written.</p>
      <button class="btn btn-block" data-act="ed-detect" ${busy ? 'disabled' : ''}>${icon('scan')} ${e.checked ? 'Check again' : 'Check for AI'} · ${esc(E.detectPrice)}</button>
      ${e.error?.where === 'check' ? err : ''}
    </section>
    <section class="ed-block" id="ed-result">
      <h3>2. Result</h3>
      ${score}
      ${result}
      <ul class="legend" aria-label="Colors in the document">
        <li><span class="sw sw-ai"></span>Looks AI</li><li><span class="sw sw-sel"></span>Selected</li>
        <li><span class="sw sw-ins"></span>New text</li><li><span class="sw sw-del"></span>Removed</li>
      </ul>
    </section>
    <section class="ed-block" id="ed-fix">
      <h3>3. Fix</h3>
      ${busy ? `<div class="loading small"><span class="spinner" aria-hidden="true"></span>${esc(busy)}</div>` : ''}
      ${e.error?.where === 'fix' ? err : ''}
      <button class="btn btn-primary btn-block" data-act="ed-humanize-sel" ${edHasSel() && !busy ? '' : 'disabled'}>${icon('sparkles')} Humanize selection · ${esc(E.humanizePrice)}</button>
      <button class="btn btn-block" data-act="ed-humanize-all" ${flags.length && !busy ? '' : 'disabled'}>Humanize all AI parts${flags.length ? ` (${flags.length})` : ''}</button>
      <p class="small muted">Select any text and a Humanize button appears next to it. Shortcut: Ctrl/⌘ + Shift + H.</p>
      ${suggs.length ? `<div class="ed-review" role="group" aria-label="Changes to review">
          <b>${suggs.length} change${suggs.length > 1 ? 's' : ''} to review</b>
          <div><button class="btn btn-sm" data-act="ed-accept-all">Accept all</button><button class="btn btn-sm btn-ghost" data-act="ed-reject-all">Reject all</button></div>
        </div>` : ''}
    </section>`;
}

function refreshEdPanel(focusSel) {
  const body = $('#ed-panel-body');
  if (!body) return;
  body.innerHTML = edPanelHtml();
  body.dataset.flags = edFlags().length;    // lets typing refresh the panel only when the count changes
  if (focusSel) $(focusSel)?.focus();
}

function edSave() {
  const doc = $('#doc');
  if (!doc) return;
  const e = edState();
  const last = e.versions[0];
  if (!last || Date.now() - last.at > ED_VERSION_EVERY_MS) edSnapshot('Autosave', e.html);
  e.html = doc.innerHTML.replace(/ is-current/g, '');
  edStatus();
  if (!state.signedIn) return;
  $('#ed-saved').textContent = 'Saving…';
  clearTimeout(edSavedTimer);
  edSavedTimer = setTimeout(() => {
    const ok = edPersist(), s = $('#ed-saved');
    if (s) s.textContent = ok ? 'All changes saved' : 'Not saved: browser storage is full. Export a copy.';
  }, 500);
}

// Plain text the detector sees: suggested deletions and buttons left out, one block per paragraph
function edPlainText() {
  const doc = $('#doc');
  if (!doc) return '';
  const clone = doc.cloneNode(true);
  clone.querySelectorAll('del, .sugg-actions').forEach(n => n.remove());
  const blocks = [...clone.querySelectorAll('h1, h2, h3, p, li')];
  return (blocks.length ? blocks.map(b => b.textContent) : [clone.textContent]).map(t => t.trim()).filter(Boolean).join('\n\n');
}

// The document as clean HTML for export: unreviewed suggestions keep the original text
function edCleanHtml() {
  const doc = $('#doc');
  const root = doc ? doc.cloneNode(true) : Object.assign(document.createElement('div'), { innerHTML: edState().html });
  root.querySelectorAll('.sugg').forEach(s => s.replaceWith(document.createTextNode(s.querySelector('del')?.textContent || '')));
  root.querySelectorAll('.ai-flag, .ed-pending').forEach(edUnwrap);
  return root.innerHTML;
}

function edStatus() {
  const doc = $('#doc');
  if (!doc) return;
  const clone = doc.cloneNode(true);
  clone.querySelectorAll('del, .sugg-actions').forEach(n => n.remove());
  const blocks = [...clone.querySelectorAll('h1, h2, h3, p, li')];
  const text = (blocks.length ? blocks.map(b => b.textContent) : [clone.textContent]).join(' ');
  const words = countWords(text);
  $('#st-words').textContent = `${fmtNum(words)} words`;
  $('#st-chars').textContent = `${fmtNum(text.replace(/\s+/g, ' ').trim().length)} characters`;
  const pages = Math.max(1, Math.ceil(words / 500));
  $('#st-pages').textContent = `${pages} page${pages > 1 ? 's' : ''}`;
}

/* Selection: remember it, update toolbar state and show the mini "Humanize" bar */
const selPop = $('#sel-pop');
function showSelPop(range, text) {
  $('#sel-pop-words').textContent = `${countWords(text)} words`;
  selPop.hidden = false;
  const r = range.getBoundingClientRect();
  const w = selPop.offsetWidth, h = selPop.offsetHeight;
  let top = r.top - h - 8;
  if (top < 8) top = r.bottom + 8;
  selPop.style.top = top + 'px';
  selPop.style.left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8) + 'px';
}
function hideSelPop() { selPop.hidden = true; }
selPop.addEventListener('mousedown', (e) => e.preventDefault());   // keep the text selected

let edSelWasActive = false;
document.addEventListener('selectionchange', () => {
  const doc = $('#doc');
  if (!doc) { hideSelPop(); return; }
  const sel = getSelection();
  if (sel.rangeCount && doc.contains(sel.anchorNode) && doc.contains(sel.focusNode)) {
    edRange = sel.getRangeAt(0).cloneRange();
    edCaret = edRange.cloneRange();
    edToolbarState();
    const e = edState();
    if (e.tab === 'comments') {
      e.cmtQuote = edHasSel() ? edRange.toString().replace(/\s+/g, ' ').trim() : '';
      const q = $('#ed-cmt-quote');
      if (q) { q.textContent = e.cmtQuote.slice(0, 180); q.hidden = !e.cmtQuote; }
    }
    if (edHasSel() && !edState().busy) showSelPop(edRange, edRange.toString());
    else hideSelPop();
  } else if (!selPop.contains(document.activeElement)) {
    if (!sel.rangeCount || !sel.getRangeAt(0).collapsed) edRange = null;
    hideSelPop();
  }
  const active = edHasSel();
  if (active !== edSelWasActive) {
    edSelWasActive = active;
    const btn = $('[data-act="ed-humanize-sel"]', $('#ed-panel-body') || document);
    if (btn) btn.disabled = !active || !!edState().busy;
  }
});

function edToolbarState() {
  ED_TOGGLES.forEach(cmd => {
    const b = $(`.tb-btn[data-cmd="${cmd}"]`);
    try { b?.setAttribute('aria-pressed', String(document.queryCommandState(cmd))); } catch {}
  });
  const block = edRange?.startContainer.parentElement?.closest('h1, h2, h3, p, li');
  const sel = $('#ed-block');
  if (sel && block) sel.value = ['h1', 'h2', 'h3'].includes(block.tagName.toLowerCase()) ? block.tagName.toLowerCase() : 'p';
}

function edRestoreSel() {
  const doc = $('#doc');
  doc.focus({ preventScroll: true });
  if (edRange) { const s = getSelection(); s.removeAllRanges(); s.addRange(edRange); }
}

function bindEditor() {
  const e = edState(), doc = $('#doc');
  edRange = null; edCaret = null; edSelWasActive = false;
  if (!e.busy) $$('#doc .ed-pending').forEach(edUnwrap);    // left over from a run interrupted by a reload
  edStatus();
  $('#ed-panel-body').dataset.flags = edFlags().length;
  $('#ed-title').addEventListener('input', (ev) => { e.title = ev.target.value; ev.target.title = e.title; edSave(); });
  $('#ed-title').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); doc.focus(); } });
  doc.addEventListener('input', () => {
    edSave();
    if (edFlags().length !== Number($('#ed-panel-body')?.dataset.flags || -1)) refreshEdPanel();
  });
  doc.addEventListener('keydown', (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && ev.key.toLowerCase() === 'h') { ev.preventDefault(); edHumanize('sel'); }
    if (ev.key === 'Escape') hideSelPop();
  });
  $('#ed-scroll').addEventListener('scroll', () => { if (!selPop.hidden && edRange) showSelPop(edRange, edRange.toString()); }, { passive: true });
  const toolbar = $('.ed-toolbar');
  toolbar.addEventListener('mousedown', (ev) => { if (ev.target.closest('.tb-btn')) ev.preventDefault(); });
  toolbar.addEventListener('click', (ev) => {
    const b = ev.target.closest('.tb-btn');
    if (!b) return;
    edRestoreSel();
    document.execCommand(b.dataset.cmd, false, null);
    edSave(); edToolbarState();
  });
  $('#ed-block').addEventListener('change', (ev) => {
    edRestoreSel();
    document.execCommand('formatBlock', false, ev.target.value);
    edSave();
  });
  $('#ed-file').addEventListener('change', (ev) => { const f = ev.target.files[0]; ev.target.value = ''; if (f) edOpenFile(f); });
  // The Cite form is re-rendered with the panel, so listen on the panel
  const panel = $('#ed-panel-body');
  panel.addEventListener('submit', (ev) => { if (ev.target.id === 'ed-cite-form') { ev.preventDefault(); edCiteSearch(); } });
  panel.addEventListener('change', (ev) => {
    if (ev.target.id !== 'ed-cite-style') return;
    e.cite.style = ev.target.value;
    if (e.cite.results && e.cite.query) edCiteSearch();
  });
}

// Text range of a sentence in the document, ignoring whitespace differences. Text inside suggestions
// (and, unless allowFlags, inside AI marks) is skipped.
function edFindRange(sentence, { allowFlags = false } = {}) {
  const doc = $('#doc');
  const needle = String(sentence || '').replace(/\s+/g, ' ').trim();
  if (!doc || needle.length < 4) return null;
  const skip = allowFlags ? '.sugg' : '.sugg, .ai-flag';
  const walker = document.createTreeWalker(doc, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement.closest(skip) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  let text = '';
  const map = [];
  while (walker.nextNode()) { map.push({ node: walker.currentNode, start: text.length }); text += walker.currentNode.nodeValue; }
  const find = (s) => {
    const re = s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s+');
    try { return new RegExp(re).exec(text); } catch { return null; }
  };
  const m = find(needle) || (needle.length > 80 ? find(needle.slice(0, 80)) : null);
  if (!m) return null;
  const at = (idx) => { for (let i = map.length - 1; i >= 0; i--) if (idx >= map[i].start) return { node: map[i].node, offset: idx - map[i].start }; return null; };
  const start = at(m.index), end = at(m.index + m[0].length);
  if (!start || !end) return null;
  const r = document.createRange();
  r.setStart(start.node, Math.min(start.offset, start.node.length));
  r.setEnd(end.node, Math.min(end.offset, end.node.length));
  return r;
}

// Wrap every text piece of a range in <mark class="ai-flag" data-part>; pieces after the first get data-cont
function edMarkRange(range, part) {
  const rootNode = range.commonAncestorContainer;
  const walker = document.createTreeWalker(rootNode.nodeType === Node.TEXT_NODE ? rootNode.parentNode : rootNode, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) if (range.intersectsNode(walker.currentNode)) nodes.push(walker.currentNode);
  let first = true;
  nodes.forEach(node => {
    const start = node === range.startContainer ? range.startOffset : 0;
    const end = node === range.endContainer ? range.endOffset : node.length;
    if (end <= start || !node.nodeValue.slice(start, end).trim()) return;
    if (end < node.length) node.splitText(end);
    const target = start > 0 ? node.splitText(start) : node;
    const mark = document.createElement('mark');
    mark.className = 'ai-flag';
    mark.dataset.part = part;
    if (!first) mark.dataset.cont = '1';
    first = false;
    target.replaceWith(mark);
    mark.append(target);
  });
}

// A flagged sentence that now holds a change is no longer "AI-looking"; splitting a mark (e.g. by a partial
// selection) can leave several first pieces, so only the first piece of each part stays without data-cont
function edTidyFlags(root) {
  const marks = [...root.querySelectorAll('.ai-flag')];
  const drop = new Set(marks.filter(m => m.querySelector('.sugg') || m.closest('.sugg')).map(m => m.dataset.part));
  const seen = new Set();
  marks.forEach(m => {
    if (drop.has(m.dataset.part) || !m.textContent.trim()) { edUnwrap(m); return; }
    if (seen.has(m.dataset.part)) m.dataset.cont = '1'; else { seen.add(m.dataset.part); delete m.dataset.cont; }
  });
  root.normalize();
}

function edFlagSentences(sentences) {
  const doc = $('#doc');
  $$('#doc .ai-flag').forEach(edUnwrap);
  doc.normalize();
  const stamp = Date.now().toString(36);
  sentences.forEach((s, i) => { const r = edFindRange(s); if (r) edMarkRange(r, `${stamp}-${i}`); });
  edState().flagIdx = -1;
}

async function edDetect() {
  if (!state.signedIn) return signUp();
  const e = edState();
  if (e.busy) return;
  const text = edPlainText();
  if (countWords(text) < 5) { toast('Add some text before checking.'); return; }
  e.busy = 'Checking the document…'; e.error = null;
  refreshEdPanel();
  try {
    const data = await API.editor.detect(text);
    if (typeof data.balance === 'number') state.balance = data.balance;
    Object.assign(e, { busy: false, checked: true, aiPercent: data.ai_percentage });
    if (currentRoute() === 'workspace') {
      edFlagSentences(data.flagged_sentences || []);
      edSave();
      refreshEdPanel(edFlags().length ? '[data-act="ed-flag"][data-dir="1"]' : null);
    }
    const n = $$('#doc .ai-flag:not([data-cont])').length;
    toast(`${data.ai_percentage}% AI · ${n ? `${n} part${n > 1 ? 's' : ''} marked` : 'nothing to mark'}`);
    renderHeader(); loadCredits();
  } catch (err) {
    e.busy = false;
    const info = apiErrorInfo(err, { intent: 'workspace' });
    if (!info.handled) e.error = { ...info, where: 'check' };
    refreshEdPanel();
  }
}

function edGoFlag(dir) {
  const flags = edFlags(), e = edState();
  if (!flags.length) return;
  e.flagIdx = ((e.flagIdx + dir) % flags.length + flags.length) % flags.length;
  $$('#doc .ai-flag').forEach(f => f.classList.remove('is-current'));
  const f = flags[e.flagIdx];
  edParts(f).forEach(m => m.classList.add('is-current'));
  f.scrollIntoView({ block: 'center', behavior: 'smooth' });
  const r = edPartRange(f, true);
  const s = getSelection(); s.removeAllRanges(); s.addRange(r);
  edRange = r.cloneRange();
  $('#ed-flag-pos').textContent = `${e.flagIdx + 1} / ${flags.length}`;
  setTimeout(() => { if (edHasSel()) showSelPop(edRange, edRange.toString()); }, 350);
}

/* Split a selection into one range per paragraph, so each change stays inside its block */
function edSplitByBlocks(range) {
  const blocks = $$('#doc h1, #doc h2, #doc h3, #doc p, #doc li').filter(b => range.intersectsNode(b));
  if (!blocks.length) return [range.cloneRange()];
  return blocks.map(b => {
    const r = document.createRange();
    r.selectNodeContents(b);
    if (b.contains(range.startContainer)) r.setStart(range.startContainer, range.startOffset);
    if (b.contains(range.endContainer)) r.setEnd(range.endContainer, range.endOffset);
    return r;
  }).filter(r => r.toString().trim());
}

/* Several parts go to the humanizer as one run: each part sits under its own marker line, and the
   rewritten text is split back on those markers (same format as the classic workspace). */
const ED_MARK = (i) => `⟦WS:${i}⟧`;
function edPack(texts) {
  return [`IMPORTANT: Keep every marker line like ${ED_MARK(0)} exactly unchanged on its own line. Only rewrite the prose under each marker. Do not merge sections.`, '',
    ...texts.flatMap((t, i) => [ED_MARK(i), t, ''])].join('\n');
}
function edUnpack(output, count) {
  const text = String(output || '');
  const patterns = [/⟦\s*WS\s*:\s*(\d+)\s*⟧/gi, /\[\s*WS\s*:\s*(\d+)\s*\]/gi, /(?:^|\n)\s*(?:#{1,3}\s*)?(?:\[+\s*)?WS\s*[:_-]?\s*(\d+)\s*(?:\]+)?\s*(?=\n|$)/gi];
  let found = [];
  for (const re of patterns) {
    found = [...text.matchAll(re)].map(m => ({ index: m.index, id: Number(m[1]), len: m[0].length }));
    if (found.length) break;
  }
  if (!found.length) return null;
  found.sort((a, b) => a.index - b.index);
  const chunks = found.map((m, i) => ({ id: m.id, text: text.slice(m.index + m.len, i + 1 < found.length ? found[i + 1].index : text.length).trim() }));
  const byId = new Array(count);
  chunks.forEach(c => { if (c.id >= 0 && c.id < count && byId[c.id] == null) byId[c.id] = c.text; });
  if (byId.filter(x => typeof x === 'string').length === count) return byId;
  return chunks.length === count ? chunks.map(c => c.text) : null;   // markers renumbered: fall back to order
}

function edMakeSugg(oldText, newText) {
  const span = document.createElement('span');
  span.className = 'sugg';
  span.contentEditable = 'false';
  span.innerHTML = `<del>${esc(oldText)}</del><ins>${esc(newText)}</ins><span class="sugg-actions">` +
    `<button type="button" class="sugg-btn" data-act="ed-accept" aria-label="Accept change" data-tip-title="Accept" data-tip-desc="Keep the new text" data-tip-pos="bottom">${icon('check')}</button>` +
    `<button type="button" class="sugg-btn" data-act="ed-reject" aria-label="Reject change" data-tip-title="Reject" data-tip-desc="Keep the original text" data-tip-pos="bottom">${icon('close')}</button></span>`;
  return span;
}

async function edHumanize(kind) {
  if (!state.signedIn) return signUp();
  const e = edState();
  if (e.busy) return;
  const ranges = kind === 'sel' ? (edHasSel() ? edSplitByBlocks(edRange) : []) : edFlags().map(f => edPartRange(f));
  if (!ranges.length) return;
  const texts = ranges.map(r => r.toString().replace(/\s+/g, ' ').trim());
  const words = texts.reduce((n, t) => n + countWords(t), 0);
  if (words > ED_MAX_HUMANIZE_WORDS) {
    toast(`Humanize up to ${fmtNum(ED_MAX_HUMANIZE_WORDS)} words at a time. This is ${fmtNum(words)} words.`);
    return;
  }
  hideSelPop();
  getSelection().removeAllRanges();
  edRange = null;
  edSnapshot('Before humanize');
  // Lock each part while the run is in progress, so edits elsewhere can't shift it
  [...ranges].reverse().forEach((r, k) => {
    const span = document.createElement('span');
    span.className = 'ed-pending';
    span.contentEditable = 'false';
    span.dataset.i = String(ranges.length - 1 - k);
    span.append(r.extractContents());
    r.insertNode(span);
  });
  e.busy = `Humanizing ${ranges.length > 1 ? ranges.length + ' parts' : 'the selection'}… this can take a minute`;
  e.error = null;
  edSave(); refreshEdPanel();

  let parts = null, failure = null;
  try {
    const data = await API.humanize(texts.length === 1 ? texts[0] : edPack(texts), 'workspace_partial');
    if (typeof data.balance === 'number') state.balance = data.balance;
    parts = texts.length === 1 ? [String(data.humanized_text || '')] : edUnpack(data.humanized_text, texts.length);
    if (!parts) failure = { message: 'The rewritten text came back in a different shape, so nothing was changed. Try a smaller selection.' };
  } catch (err) {
    const info = apiErrorInfo(err, { intent: 'workspace' });
    if (!info.handled) failure = info;
  }

  // The user may have left the Editor meanwhile: apply the result to the saved document then
  const onPage = currentRoute() === 'workspace' && $('#doc');
  const root = onPage ? $('#doc') : Object.assign(document.createElement('div'), { innerHTML: e.html });
  let changed = 0;
  root.querySelectorAll('.ed-pending').forEach(span => {
    const i = Number(span.dataset.i), old = span.textContent;
    const neu = parts ? String(parts[i] || '').replace(/\s+/g, ' ').trim() : '';
    if (!neu || neu === old.replace(/\s+/g, ' ').trim()) { edUnwrap(span); return; }
    span.replaceWith(old.match(/^\s*/)[0], edMakeSugg(old.trim(), neu), old.match(/\s*$/)[0]);
    changed++;
  });
  edTidyFlags(root);
  e.busy = false;
  if (failure) e.error = { ...failure, where: 'fix' };
  if (onPage) { edSave(); refreshEdPanel(); } else { e.html = root.innerHTML; edPersist(); }
  renderHeader(); loadCredits();
  if (failure) return;
  if (!changed) { toast('The humanizer returned the same text. Nothing to review.'); return; }
  toast(`${changed} change${changed > 1 ? 's' : ''} to review: accept or reject each one`);
  if (onPage) {
    const first = $('#doc .sugg [data-act="ed-accept"]');
    first?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    first?.focus({ preventScroll: true });
  }
}

function edResolve(sugg, accept) {
  const text = sugg.querySelector(accept ? 'ins' : 'del').textContent;
  const next = sugg.nextElementSibling;
  sugg.replaceWith(document.createTextNode(text));
  $('#doc').normalize();
  edSave(); refreshEdPanel();
  // Keep keyboard users moving through the changes
  ($('#doc .sugg [data-act="ed-accept"]') || $('#doc'))?.focus({ preventScroll: true });
}

function edOpenMenu(btn, items) {
  edCloseMenu();
  const menu = document.createElement('div');
  menu.className = 'menu'; menu.id = 'ed-menu'; menu.setAttribute('role', 'menu');
  menu.innerHTML = items.map(i => i.disabled
    ? `<button role="menuitem" disabled aria-disabled="true" class="muted">${esc(i.label)}</button>`
    : `<button role="menuitem" data-act="${i.act}" data-value="${esc(i.value || '')}">${esc(i.label)}</button>`).join('');
  document.body.append(menu);
  const r = btn.getBoundingClientRect();
  menu.style.top = r.bottom + 4 + 'px';
  menu.style.left = Math.max(8, r.right - menu.offsetWidth) + 'px';
  menu.dataset.opener = btn.dataset.act;
  btn.setAttribute('aria-expanded', 'true');
  menu.querySelector('button:not([disabled])')?.focus();
}
function edCloseMenu(focusOpener) {
  const menu = $('#ed-menu');
  if (!menu) return false;
  const opener = $(`[data-act="${menu.dataset.opener}"]`);
  opener?.setAttribute('aria-expanded', 'false');
  menu.remove();
  if (focusOpener) opener?.focus();
  return true;
}

function edAction(act, el) {
  const e = edState();
  switch (act) {
    case 'ed-tab': e.tab = el.dataset.tab; render(); $(`#ed-tab-${e.tab}`).focus(); break;
    case 'ed-detect': edDetect(); break;
    case 'ed-flag': edGoFlag(Number(el.dataset.dir)); break;
    case 'ed-humanize-sel': edHumanize('sel'); break;
    case 'ed-humanize-all': edHumanize('all'); break;
    case 'ed-accept': edResolve(el.closest('.sugg'), true); break;
    case 'ed-reject': edResolve(el.closest('.sugg'), false); break;
    case 'ed-accept-all': case 'ed-reject-all': {
      const accept = act === 'ed-accept-all';
      edSuggs().forEach(s => s.replaceWith(document.createTextNode(s.querySelector(accept ? 'ins' : 'del').textContent)));
      $('#doc').normalize(); edSave(); refreshEdPanel();
      toast(accept ? 'All changes accepted' : 'All changes rejected');
      $('[data-act="ed-humanize-all"]')?.focus();
      break;
    }
    case 'ed-zoom':
      e.zoom = Math.min(2, Math.max(0.5, Math.round((e.zoom + Number(el.dataset.step)) * 10) / 10));
      $('#doc').style.zoom = e.zoom; $('#st-zoom').textContent = Math.round(e.zoom * 100) + '%';
      break;
    case 'ed-open':
      edOpenMenu(el, [{ label: 'Open a file (.docx, .pdf, .txt)', act: 'ed-open-file' }, { label: 'New blank document', act: 'ed-new' }]);
      break;
    case 'ed-open-file': edCloseMenu(); $('#ed-file').click(); break;
    case 'ed-new': edCloseMenu(); edReplaceDoc('Untitled document', '<p><br></p>', 'Before new document'); $('#doc')?.focus(); break;
    case 'ed-export':
      edOpenMenu(el, [{ label: 'Download as .docx', act: 'ed-export-as', value: 'docx' }, { label: 'Print or save as PDF', act: 'ed-export-as', value: 'pdf' }]);
      break;
    case 'ed-export-as': edCloseMenu(true); if (el.dataset.value === 'pdf') edPrint(); else edExportDocx(); break;
    case 'ed-versions':
      edOpenMenu(el, [{ label: 'Current version · now', disabled: true },
        ...(e.versions.length
          ? e.versions.map((v, i) => ({ label: `Restore ${fmtWhen(v.at)}${v.label && v.label !== 'Autosave' ? ` · ${v.label}` : ''}`, act: 'ed-restore', value: String(i) }))
          : [{ label: 'Earlier versions appear here as you edit', disabled: true }])]);
      break;
    case 'ed-restore': {
      edCloseMenu(true);
      const v = e.versions[Number(el.dataset.value)];
      if (!v || e.busy) break;
      edSnapshot('Before restoring');
      Object.assign(e, { title: v.title, html: v.html, flagIdx: -1 });
      edPersist(); render();
      toast(`Restored the version from ${fmtWhen(v.at)}`);
      break;
    }
    case 'ed-cite-insert': case 'ed-cite-ref': edCiteUse(act === 'ed-cite-insert' ? 'insert' : 'reference', Number(el.dataset.i), el); break;
    case 'ed-cmt-add': {
      const box = $('#ed-cmt-text'), text = box.value.trim();
      if (!text) { box.focus(); toast('Write a comment first.'); break; }
      e.comments.unshift({ id: 'c' + Date.now(), quote: e.cmtQuote.slice(0, 300), text: text.slice(0, 2000), at: Date.now() });
      e.cmtQuote = '';
      edPersist(); refreshEdPanel('#ed-cmt-text');
      break;
    }
    case 'ed-cmt-del': e.comments = e.comments.filter(c => c.id !== el.dataset.id); edPersist(); refreshEdPanel('#ed-cmt-text'); break;
    case 'ed-cmt-find': {
      const c = e.comments.find(x => x.id === el.dataset.id), r = c && edFindRange(c.quote, { allowFlags: true });
      if (!r) { toast('This text is no longer in the document.'); break; }
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      r.startContainer.parentElement.scrollIntoView({ block: 'center', behavior: 'smooth' });
      break;
    }
  }
}

async function edOpenFile(file) {
  if (!/\.(docx|pdf|txt)$/i.test(file.name)) { toast('Please choose a .docx, .pdf or .txt file'); return; }
  try {
    const text = await API.extractText(file);
    const paras = text.split(/\n\s*\n|\n/).map(p => p.trim()).filter(Boolean);
    if (!paras.length) { toast('No text found in this file.'); return; }
    edReplaceDoc(file.name.replace(/\.[^.]+$/, ''), paras.map(p => `<p>${esc(p)}</p>`).join(''), `Before opening “${file.name}”`);
    toast(`Opened “${file.name}”. The previous document is in Version history.`);
  } catch (err) {
    const info = apiErrorInfo(err, { intent: 'workspace' });
    if (!info.handled) toast(info.message);
  }
}

function edSaveBlob(blob, name) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

async function edExportDocx() {
  if (!state.signedIn) return signUp();
  const e = edState(), pending = edSuggs().length;
  try {
    const { blob, name } = await API.editor.export(e.title, edCleanHtml());
    edSaveBlob(blob, name);
    toast(pending ? `Downloaded ${name}. ${pending} unreviewed change${pending > 1 ? 's' : ''} kept the original text.` : `Downloaded ${name}`);
  } catch (err) {
    const info = apiErrorInfo(err, { intent: 'workspace' });
    if (!info.handled) toast(info.message);
  }
}

// PDF through the browser's print dialog ("Save as PDF"), with only the document on the page
function edPrint() {
  const frame = document.createElement('iframe');
  frame.setAttribute('aria-hidden', 'true');
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0';
  document.body.append(frame);
  const d = frame.contentDocument;
  d.open();
  d.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(edState().title)}</title><style>
    @page { margin: 2.5cm; } body { margin: 0; color: #000; font: 12pt/1.6 "Times New Roman", Times, serif; }
    h1 { font-size: 20pt; } h2 { font-size: 15pt; } h3 { font-size: 13pt; } p { margin: 0 0 10pt; }
  </style></head><body>${edCleanHtml()}</body></html>`);
  d.close();
  frame.contentWindow.addEventListener('afterprint', () => frame.remove());
  setTimeout(() => frame.remove(), 120000);
  frame.contentWindow.focus();
  frame.contentWindow.print();
}

async function edCiteSearch() {
  const c = edState().cite;
  if (!state.signedIn) return signUp();
  const q = $('#ed-cite-q'), style = $('#ed-cite-style');
  if (q) c.query = q.value.trim();
  if (style) c.style = style.value;
  if (!c.query || c.busy) { q?.focus(); return; }
  c.busy = true; c.error = '';
  refreshEdPanel();
  try {
    const data = await API.editor.citeSearch(c.query, c.style);
    c.results = data.results || [];
  } catch (err) {
    const info = apiErrorInfo(err, { intent: 'workspace' });
    c.error = info.handled ? '' : info.message;
  }
  c.busy = false;
  if (edState().tab === 'cite') refreshEdPanel(c.results?.length ? '[data-act="ed-cite-insert"]' : '#ed-cite-q');
}

async function edCiteUse(kind, i, btn) {
  const c = edState().cite, r = c.results?.[i];
  if (!r) return;
  const at = edCaret ? edCaret.cloneRange() : null;     // where the cursor was before clicking
  if (btn) btn.disabled = true;
  try {
    const data = await API.editor.citeUse(kind, r.doi);
    if (typeof data.balance === 'number') state.balance = data.balance;
    if (kind === 'insert') edInsertCitation(r.intext || `(${r.label || ''})`, at); else edAddReference(r.reference || r.title);
    renderHeader(); loadCredits();
  } catch (err) {
    const info = apiErrorInfo(err, { intent: 'workspace' });
    if (!info.handled) toast(info.message);
  } finally {
    if (btn && btn.isConnected) btn.disabled = false;
  }
}

function edInsertCitation(text, at) {
  const doc = $('#doc');
  if (!doc) return;
  let r = at && doc.contains(at.endContainer) && !at.endContainer.parentElement?.closest('.sugg') ? at : null;
  if (!r) { r = document.createRange(); r.selectNodeContents($$('#doc p').pop() || doc); }
  r.collapse(false);
  const node = document.createTextNode(' ' + text);
  r.insertNode(node);
  r.setStartAfter(node);
  edCaret = r.cloneRange();
  edSave();
  toast(`Citation ${text} inserted`);
}

function edAddReference(ref) {
  const doc = $('#doc');
  if (!doc || !ref) return;
  let head = $$('#doc h1, #doc h2, #doc h3').find(h => /^(references?|reference list|bibliography|works cited)$/i.test(h.textContent.trim()));
  const p = document.createElement('p');
  p.textContent = ref;
  if (!head) {
    head = document.createElement('h2');
    head.textContent = 'References';
    doc.append(head, p);
  } else {
    let last = head;
    while (last.nextElementSibling?.tagName === 'P') last = last.nextElementSibling;
    last.after(p);
  }
  p.scrollIntoView({ block: 'center', behavior: 'smooth' });
  edSave();
  toast('Reference added to the document');
}

/* ---------- Slides: topic → (optional settings) → generate → edit text & switch design for free ---------- */
// The generated deck is kept in this browser (one per account) so it survives reloads and "Continue" on Home
const slKey = () => 'slides-' + (BOOT.user ? BOOT.user.id : 'guest');
const SL_SAVED = ['topic', 'count', 'photos', 'designId', 'deck', 'meta', 'current'];
const slState = () => {
  if (state.slides) return state.slides;
  const s = state.slides = {
    stage: 'setup', topic: '', file: null, ...structuredClone(CONFIG.slides.defaults),
    designId: CONFIG.slides.designs[0].id, filter: 'All', deck: [], meta: {}, current: 0, error: null, downloading: false,
  };
  const saved = BOOT.user ? store.get(slKey(), null) : null;
  if (saved && Array.isArray(saved.deck) && saved.deck.length) {
    SL_SAVED.forEach(k => { if (k in saved) s[k] = saved[k]; });
    if (!CONFIG.slides.designs.some(d => d.id === s.designId)) s.designId = CONFIG.slides.designs[0].id;
    s.current = Math.max(0, Math.min(Number(s.current) || 0, s.deck.length - 1));
    s.stage = 'done';
  }
  return s;
};
const slSave = () => {
  const s = state.slides;
  if (!state.signedIn || !s) return;
  store.set(slKey(), s.stage === 'done' ? Object.fromEntries(SL_SAVED.map(k => [k, s[k]])) : null);
};
const slDesign = () => CONFIG.slides.designs.find(d => d.id === slState().designId) || CONFIG.slides.designs[0];
const slTitle = () => { const s = slState(); return s.topic.trim() || (s.file ? s.file.name.replace(/\.[^.]+$/, '') : ''); };
// A short bare topic is researched on the web first; an attached file or long pasted text is not
const slResearch = (s) => !s.file && !!s.topic.trim() && s.topic.trim().length <= CONFIG.slides.researchMaxChars;
// Mirrors the server: a count written in the request ("10 slides", "12 слайдов") wins over the picker
const SL_COUNT_RE = /(?<!\d)(\d{1,2})\s*[- ]?\s*(?:slides?\b|слайд)/gi;
const slCount = (s) => {
  const S = CONFIG.slides, [min, max] = [S.counts[0], S.counts[S.counts.length - 1]];
  for (const m of `${s.topic}\n${s.file?.text || ''}`.matchAll(SL_COUNT_RE)) {
    const n = Number(m[1]);
    if (n >= min && n <= max) return n;
  }
  return Number(s.count);
};
const slPrice = (s) => {
  const base = parseInt(CONFIG.slides.price, 10);
  return Number.isNaN(base) ? CONFIG.slides.price : `${base + CONFIG.slides.perSlidePrice * slCount(s)} credits`;
};

// The API deck has the title slide in deck.title / subtitle / cover_image; the viewer treats it as slide 1
function slFromDeck(deck) {
  const { slides = [], title = '', subtitle = '', cover_image: image = null, ...meta } = deck || {};
  return { meta, deck: [{ layout: 'cover', title, subtitle, image }, ...slides] };
}
function slToDeck(s) {
  const [cover, ...slides] = s.deck;
  return { ...s.meta, title: cover.title, subtitle: cover.subtitle || '', cover_image: cover.image || null, theme: s.designId, slides };
}

const SL_COVER_LAYOUTS = ['cover', 'section', 'closing'];
const SL_PHOTO_LAYOUTS = ['cover', 'section', 'image'];
function slideHtml(slide, d, { editable = false, photos = true } = {}) {
  const f = (field, tag, cls, text, label) => `<${tag} class="${cls}" ${editable
    ? `contenteditable="true" spellcheck="true" data-field="${field}" aria-label="${label}"` : ''}>${esc(text || '')}</${tag}>`;
  const list = (items, path) => (items && items.length
    ? `<ul class="s-list">${items.map((b, i) => f(`${path}.${i}`, 'li', '', b, `Point ${i + 1}`)).join('')}</ul>` : '');
  const items = (cls, tag, label) => `<${tag} class="${cls}">${(slide.items || []).map((it, i) => `<li>
    ${f(`items.${i}.heading`, 'b', 's-item-h', it.heading, `${label} ${i + 1} heading`)}${f(`items.${i}.text`, 'p', '', it.text, `${label} ${i + 1} text`)}</li>`).join('')}</${tag}>`;
  const layout = slide.layout || 'bullets';
  // Title, section and closing slides use the theme's cover colors; content slides use its page colors
  const pal = SL_COVER_LAYOUTS.includes(layout) || !d.page ? { bg: d.bg, fg: d.fg, accent: d.accent } : d.page;
  const imgUrl = photos && SL_PHOTO_LAYOUTS.includes(layout) && slide.image && slide.image.url;
  const withPhoto = !!imgUrl || (photos && slide.photo);
  const title = f('title', 'h3', 's-title', slide.title, 'Slide title');
  const sub = slide.subtitle || editable ? f('subtitle', 'p', 's-sub', slide.subtitle, 'Subtitle') : '';
  let inner;
  switch (layout) {
    case 'cover': case 'section': inner = `<div class="s-inner s-title-slide">${title}${sub}</div>`; break;
    case 'closing': inner = `<div class="s-inner s-end-slide">${title}${sub}${list(slide.bullets, 'bullets')}</div>`; break;
    case 'cards': inner = `<div class="s-inner">${title}${items('s-cards', 'ul', 'Card')}</div>`; break;
    case 'timeline': inner = `<div class="s-inner">${title}${items('s-timeline', 'ol', 'Step')}</div>`; break;
    case 'two_column':
      inner = `<div class="s-inner">${title}<div class="s-cols">${['left', 'right'].map(side => `<div>
        ${f(`${side}.heading`, 'b', 's-item-h', (slide[side] || {}).heading, `${side === 'left' ? 'Left' : 'Right'} column heading`)}
        ${list((slide[side] || {}).bullets, `${side}.bullets`)}</div>`).join('')}</div></div>`;
      break;
    default: inner = `<div class="s-inner">${title}${list(slide.bullets, 'bullets')}</div>`;
  }
  const font = (v) => String(v).replace(/"/g, "'");
  const style = [`--s-bg:${pal.bg}`, `--s-fg:${pal.fg}`, `--s-ac:${pal.accent}`, pal.pale && `--s-pale:${pal.pale}`,
    d.headFont && `--s-hf:${font(d.headFont)}`, d.bodyFont && `--s-bf:${font(d.bodyFont)}`].filter(Boolean).join(';');
  const credit = editable && imgUrl && slide.image.credit ? `<span class="s-credit">${esc(slide.image.credit)}</span>` : '';
  const photo = imgUrl ? `<div class="s-photo s-photo-img"><img src="${esc(imgUrl)}" alt="" loading="lazy">${credit}</div>`
    : `<div class="s-photo" aria-hidden="true">${icon('image')}</div>`;
  return `<div class="slide s-${layout} ${withPhoto ? 'has-photo' : ''} ${d.upper ? 's-upper' : ''}" style="${style}">
    ${inner}${withPhoto ? photo : ''}</div>`;
}

function renderSlides() {
  const s = slState();
  return `<div class="page sl-page">
    <div class="sl-top"><button class="btn btn-sm btn-ghost" data-act="start-tour" data-tour-name="slides">${icon('help')} How it works</button></div>
    <h1 class="sl-hero">${esc(CONFIG.brand)} <span>Slides</span></h1>
    ${s.stage === 'done' ? slDoneHtml() : slSetupHtml()}
  </div>`;
}

// Same layout as the live site: one composer card (style · topic · settings · price + send), styles gallery below
function slSetupHtml() {
  const s = slState(), S = CONFIG.slides, d = slDesign(), generating = s.stage === 'generating';
  const ready = !!slTitle() && !s.file?.reading, price = slPrice(s);
  const progress = slResearch(s)
    ? 'Researching the web, then writing your slides… usually 1–3 minutes'
    : s.photos ? 'Writing your slides and picking photos… usually 30–90 seconds' : 'Writing your slides… usually 20–60 seconds';
  const select = (key, label, options, value) => `<label class="visually-hidden" for="sl-${key}">${label}</label>
    <select class="select" id="sl-${key}" data-setting="${key}" data-tip-title="${label}" data-tip-desc="" data-tip-pos="bottom" ${generating ? 'disabled' : ''}>
      ${options.map(o => `<option value="${esc(String(o.value))}" ${String(o.value) === String(value) ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`;
  return `<section class="card sl-composer" id="sl-composer" aria-label="New presentation">
      <div class="sl-comp-top" id="sl-topic-block">
        <button class="sl-style-chip" data-act="sl-jump-designs" aria-label="Design: ${esc(d.name)}. Choose another design"
          data-tip-title="Design: ${esc(d.name)}" data-tip-desc="Click to choose another one below" data-tip-pos="bottom">
          <span class="sl-aa" aria-hidden="true" style="--s-bg:${d.bg};--s-fg:${d.fg};--s-ac:${d.accent}">Aa</span>
          <span class="sl-style-name" aria-hidden="true">${esc(d.name)}</span>
        </button>
        <label class="visually-hidden" for="sl-topic">What is your presentation about?</label>
        <textarea id="sl-topic" class="sl-prompt" rows="2" placeholder="${esc(S.topicPlaceholder)}" ${generating ? 'readonly' : ''}>${esc(s.topic)}</textarea>
      </div>
      ${s.file ? `<div><span class="file-chip">${s.file.reading ? '<span class="spinner" aria-hidden="true"></span>' : icon('file')}<span class="file-name">${esc(s.file.name)}</span>
          <button class="chip-x" data-act="sl-remove-file" aria-label="Remove ${esc(s.file.name)}" ${generating ? 'disabled' : ''}>${icon('close')}</button></span>
          <span class="small muted">${s.file.reading ? 'Reading your document…'
            : s.file.truncated ? 'Long document: slides will follow its first part.' : 'Slides will follow your document.'}</span></div>` : ''}
      <div class="sl-comp-row" id="sl-settings-block">
        <button class="icon-btn sl-plus" data-act="sl-upload" aria-label="Attach a document"
          data-tip-title="Turn a document into slides" data-tip-desc="${esc(S.fileTypes)}" data-tip-pos="bottom" ${generating ? 'disabled' : ''}>${icon('plus')}</button>
        <input type="file" id="sl-file" accept="${esc(S.fileAccept)}" hidden>
        <span class="sl-mode">${icon('slides')} Slides</span>
        ${select('count', 'Number of slides', S.counts.map(n => ({ value: n, label: `${n} slides` })), s.count)}
        ${select('photos', 'Photos', [{ value: 'true', label: 'With photos' }, { value: 'false', label: 'No photos' }], String(s.photos))}
      </div>
      <div class="sl-comp-foot" id="sl-generate">
        ${generating
          ? `<span class="sl-progress" role="status"><span class="spinner" aria-hidden="true"></span>${esc(progress)}</span>`
          : `<span class="muted small" id="sl-price" data-tip-title="Price for ${slCount(s)} slides"
              data-tip-desc="${esc(`${CONFIG.slides.price} + ${CONFIG.slides.perSlidePrice} per slide. Web research and photos are included.`)}" data-tip-pos="bottom">${esc(price)}</span>`}
        <button class="sl-send" data-act="${state.signedIn ? 'sl-generate' : 'signup'}" id="sl-generate-btn"
          aria-label="${state.signedIn ? `Generate slides, ${esc(price)}` : 'Sign up to generate slides'}"
          data-tip-title="${state.signedIn ? 'Generate slides' : 'Sign up to generate'}" data-tip-desc="${esc(price)} · Enter" data-tip-pos="bottom"
          ${(ready || !state.signedIn) && !generating ? '' : 'disabled'}>${icon('send')}</button>
      </div>
      ${s.error ? `<div class="sl-error">${assignErrorHtml(s.error.message, s.error.action === 'topup'
        ? '<button class="btn btn-sm btn-primary" data-act="topup">Top up credits</button>' : '')}</div>` : ''}
    </section>
    <p class="sl-trust small muted">${esc(S.trustNote)}</p>
    ${slGalleryHtml(null)}`;
}

function slDoneHtml() {
  const s = slState(), d = slDesign(), cur = s.deck[s.current];
  return `<section class="card sl-head" aria-label="Your presentation">
      <div><h2>${esc(s.deck[0].title)}</h2>
        <span class="small muted">${s.deck.length} slides · ${esc(d.name)}</span></div>
      <div class="sl-head-actions">
        <button class="btn btn-ghost" data-act="sl-new">${icon('plus')} New presentation</button>
        <button class="btn btn-primary" id="sl-download" data-act="sl-download" ${s.downloading ? 'disabled' : ''}
          data-tip-title="Download .pptx" data-tip-desc="Opens in PowerPoint, Google Slides and Keynote" data-tip-pos="bottom">${icon('download')} ${s.downloading ? 'Preparing…' : 'Download .pptx'}</button>
      </div>
    </section>
    <section class="sl-viewer" id="sl-viewer" aria-label="Slides">
      <p class="small muted" style="margin:0">Click any text on the slide to edit it. Edits are free and save automatically.</p>
      <div class="sl-main-wrap">
        <button class="icon-btn" data-act="sl-go" data-dir="-1" aria-label="Previous slide" ${s.current ? '' : 'disabled'}>${icon('chevL')}</button>
        <div id="sl-main" aria-label="Slide ${s.current + 1} of ${s.deck.length}" role="group">${slideHtml(cur, d, { editable: true, photos: s.photos })}</div>
        <button class="icon-btn" data-act="sl-go" data-dir="1" aria-label="Next slide" ${s.current < s.deck.length - 1 ? '' : 'disabled'}>${icon('chevR')}</button>
      </div>
      <ol class="sl-thumbs" aria-label="All slides">${s.deck.map((sl, i) => `<li><button class="sl-thumb" data-act="sl-pick" data-i="${i}" aria-current="${i === s.current}" aria-label="Slide ${i + 1}: ${esc(sl.title)}">
        <span aria-hidden="true">${slideHtml(sl, d, { photos: s.photos })}</span><span class="sl-thumb-num" aria-hidden="true">${i + 1}</span></button></li>`).join('')}</ol>
    </section>
    <p class="sl-trust small muted">${esc(CONFIG.slides.trustNote)}</p>
    ${slGalleryHtml(s.deck[0])}`;
}

// Styles gallery. Before generating each card shows its own sample; after, it shows your title slide.
function slGalleryHtml(cover) {
  const s = slState(), S = CONFIG.slides;
  const designs = S.designs.filter(x => s.filter === 'All' || x.category === s.filter);
  return `<section class="sl-gallery" id="sl-designs" aria-label="Design">
    <div class="sl-filters" role="group" aria-label="Filter designs">${['All', ...S.designCategories].map(c =>
      `<button class="sl-filter" data-act="sl-filter" data-filter="${c}" aria-pressed="${s.filter === c}">${c}</button>`).join('')}
      ${s.stage === 'done' ? '<span class="small free" style="margin-left:auto">Switching designs is free</span>' : ''}</div>
    <div class="design-grid">${designs.map(x => {
      const sample = cover || { layout: 'cover', title: x.sample, subtitle: `${x.category} · 16:9`, image: x.photo ? { url: x.photo } : null, photo: true };
      return `<button class="design-card" data-act="sl-design" data-id="${x.id}" aria-pressed="${x.id === s.designId}">
        <span aria-hidden="true">${slideHtml(sample, x, { photos: true })}</span>
        <span class="design-meta"><b>${esc(x.name)}</b>${x.id === s.designId ? `${icon('check')}<span class="visually-hidden">(selected)</span>` : ''}</span>
      </button>`;
    }).join('')}</div>
  </section>`;
}

async function slGenerate() {
  const s = slState();
  if (!state.signedIn) return signUp();
  if (!slTitle() || s.stage === 'generating' || s.file?.reading) return;
  const research = slResearch(s);
  s.stage = 'generating'; s.error = null;
  rerenderSlides();
  try {
    const data = await API.presentation.generate({
      topic: s.topic.trim(),
      files: s.file?.text ? [{ name: s.file.name, text: s.file.text }] : [],
      slide_count: s.count,
      theme: s.designId,
      images: s.photos,
    });
    if (typeof data.balance === 'number') state.balance = data.balance;
    Object.assign(s, slFromDeck(data.deck), { current: 0, stage: 'done', file: null });
    slSave();
    state.docs.unshift({ id: 'd' + Date.now(), title: s.deck[0].title || slTitle(), tool: 'presentation', date: todayIso() });
    saveDocs();
    renderHeader();
    loadCredits();
    toast(research && data.research === 'failed'
      ? 'Your slides are ready. Web research was unavailable, so they are written from general knowledge.'
      : 'Your slides are ready. Click any text to edit it.');
  } catch (err) {
    s.stage = 'setup';
    const e = apiErrorInfo(err, { intent: 'presentation' });
    if (!e.handled) s.error = e;
  }
  if (currentRoute() === 'presentation') {
    rerenderSlides();
    if (s.stage === 'done') { window.scrollTo(0, 0); $('#sl-main [contenteditable]')?.focus(); }
  }
}

async function slAttach(file) {
  const s = slState();
  s.file = { name: file.name, reading: true };
  s.error = null;
  rerenderSlides('[data-act="sl-remove-file"]');
  try {
    const data = await API.presentation.extract(file);
    if (s.file?.name !== file.name) return;
    s.file = { name: data.name || file.name, text: data.text, truncated: !!data.truncated };
  } catch (err) {
    if (s.file?.name !== file.name) return;
    s.file = null;
    const e = apiErrorInfo(err, { intent: 'presentation' });
    if (!e.handled) toast(e.message);
  }
  if (currentRoute() === 'presentation' && s.stage === 'setup') rerenderSlides(s.file ? '#sl-topic' : '[data-act="sl-upload"]');
}

async function slDownload(btn) {
  const s = slState();
  if (s.downloading || !s.deck.length) return;
  s.downloading = true;
  rerenderSlides('#sl-download');
  try {
    const { blob, name } = await API.presentation.export(slToDeck(s));
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = name;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  } catch (err) {
    const e = apiErrorInfo(err, { intent: 'presentation' });
    if (!e.handled) toast(e.message);
  } finally {
    s.downloading = false;
    if (currentRoute() === 'presentation') rerenderSlides('#sl-download');
  }
}

function rerenderSlides(focusSel) {
  const y = window.scrollY;
  $('#main').innerHTML = renderSlides();
  bindSlides();
  window.scrollTo(0, y);
  if (focusSel) $(focusSel)?.focus({ preventScroll: true });
}

function slUpdatePrice() {
  const s = slState(), btn = $('#sl-generate-btn'), price = $('#sl-price'), p = slPrice(s);
  if (!price || price.textContent === p) return;
  price.textContent = p;
  price.dataset.tipTitle = `Price for ${slCount(s)} slides`;
  if (btn && state.signedIn) { btn.setAttribute('aria-label', `Generate slides, ${p}`); btn.dataset.tipDesc = `${p} · Enter`; }
}

function bindSlides() {
  const s = slState();
  const topic = $('#sl-topic');
  if (topic) {
    topic.addEventListener('input', () => {
      s.topic = topic.value;
      const btn = $('#sl-generate-btn');
      if (btn && state.signedIn) btn.disabled = !slTitle() || !!s.file?.reading;
      slUpdatePrice();
    });
    // Enter starts generation, Shift + Enter adds a new line (like a chat box)
    topic.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (slTitle()) slGenerate(); }
    });
  }
  const file = $('#sl-file');
  if (file) file.addEventListener('change', () => { if (file.files[0]) slAttach(file.files[0]); });
  $$('[data-setting]', $('#sl-settings-block') || document.createElement('div')).forEach(el => el.addEventListener('change', () => {
    const key = el.dataset.setting, v = el.value;
    s[key] = key === 'count' ? Number(v) : key === 'photos' ? v === 'true' : v;
    slUpdatePrice();
  }));
  // Inline text editing on the big slide
  const main = $('#sl-main');
  if (main) {
    main.addEventListener('input', (e) => {
      const el = e.target.closest('[data-field]'), slide = s.deck[s.current];
      if (!el) return;
      const keys = el.dataset.field.split('.');
      let target = slide;
      keys.slice(0, -1).forEach(k => { target = target[k] ?? (target[k] = {}); });
      target[keys[keys.length - 1]] = el.textContent;
      clearTimeout(slThumbTimer);
      slThumbTimer = setTimeout(slRefreshThumb, 400);
    });
    main.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.closest('[data-field]')) { e.preventDefault(); e.target.blur(); } });
  }
}
let slThumbTimer = null;
function slRefreshThumb() {
  const s = slState(), btn = $(`.sl-thumb[data-i="${s.current}"]`);
  if (btn) btn.firstElementChild.innerHTML = slideHtml(s.deck[s.current], slDesign(), { photos: s.photos });
  slSave();
}

function slAction(act, el) {
  const s = slState();
  switch (act) {
    case 'sl-upload': $('#sl-file').click(); break;
    case 'sl-remove-file': s.file = null; $('#sl-file').value = ''; rerenderSlides('[data-act="sl-upload"]'); break;
    case 'sl-jump-designs': $('#sl-designs').scrollIntoView({ behavior: 'smooth', block: 'start' }); $('.design-card[aria-pressed="true"]')?.focus({ preventScroll: true }); break;
    case 'sl-generate': slGenerate(); break;
    case 'sl-go': s.current = Math.min(s.deck.length - 1, Math.max(0, s.current + Number(el.dataset.dir))); rerenderSlides(`[data-act="sl-go"][data-dir="${el.dataset.dir}"]`); break;
    case 'sl-pick': s.current = Number(el.dataset.i); rerenderSlides(`.sl-thumb[data-i="${s.current}"]`); $('#sl-viewer').scrollIntoView({ block: 'start', behavior: 'smooth' }); break;
    case 'sl-filter': s.filter = el.dataset.filter; rerenderSlides(`[data-act="sl-filter"][data-filter="${s.filter}"]`); break;
    case 'sl-design':
      s.designId = el.dataset.id;
      slSave();
      rerenderSlides(`[data-act="sl-design"][data-id="${s.designId}"]`);
      toast(s.stage === 'done' ? `Design changed to ${slDesign().name}. No credits used.` : `Design: ${slDesign().name}`);
      break;
    case 'sl-download': slDownload(el); break;
    case 'sl-new':
      askConfirm({
        title: 'Start a new presentation?', okLabel: 'Start new', opener: el,
        text: 'Download this deck first if you need it: only the latest one is kept here. Generating a new one uses credits.',
        onOk: () => {
          const keep = slDesign().id;
          if (BOOT.user) store.set(slKey(), null);
          state.slides = null; slState().designId = keep;
          rerenderSlides(); window.scrollTo(0, 0); return $('#sl-topic');
        },
      });
      break;
  }
}

/* =========================================================
   Formatting: 1. Document → 2. Style → 3. Settings (optional), live preview, Format button
   Everything the page knows lives in one object: formatState.
   ========================================================= */
// Document and brief shared by Formatting and Work Review: add them once, use them on both pages
const workDoc = {
  file: null, text: '',            // the student's document (file or pasted text)
  briefFile: null, briefText: '',  // the brief from the lecturer
  formatted: null,                 // { styleId } after Formatting produced a new version
};
const workDocHasBrief = () => !!(workDoc.briefFile || workDoc.briefText.trim());
// Pick the tab that actually holds content, so a document added on the other page shows up
function workDocMode(current) {
  if (workDoc.file && !workDoc.text.trim()) return 'file';
  if (workDoc.text.trim() && !workDoc.file) return 'paste';
  return current;
}

/* ---------- Formatter V2 mapping (page settings <-> /api/format-v2 overrides) ---------- */
function fmtBackendStyle(id) { return { harvard: 'harvard', apa: 'apa7', mla: 'mla9', chicago: 'chicago17', ieee: 'ieee' }[id] || 'harvard'; }
function fmtAppStyle(name) { return { harvard: 'harvard', apa7: 'apa', mla9: 'mla', chicago17: 'chicago', ieee: 'ieee' }[name] || null; }
const FMT_ALIGN = { Left: 'left', Justified: 'justify', Center: 'center', Right: 'right' };
const FMT_MARGIN_IN = { normal: 1, narrow: 0.5, wide: 1.5 };

/* Backend form defaults or brief overrides -> page values (only the keys present) */
function fmtFromBackend(o) {
  const out = {};
  const pick = (list, num) => list.reduce((a, b) => (Math.abs(parseFloat(b) - num) < Math.abs(parseFloat(a) - num) ? b : a));
  if (o.style && fmtAppStyle(o.style)) out.styleId = fmtAppStyle(o.style);
  if (o.font_family) out.font = o.font_family;
  if (o.font_size_pt != null) out.size = Number(o.font_size_pt);
  if (o.line_spacing != null) out.lineSpacing = pick(CONFIG.format.options.lineSpacing, Number(o.line_spacing));
  if (o.alignment) out.alignment = { left: 'Left', justify: 'Justified', center: 'Center', right: 'Right' }[o.alignment] || 'Left';
  if (o.first_line_indent != null) out.firstLineIndent = !!o.first_line_indent;
  if (o.page_size) out.pageSize = o.page_size === 'letter' ? 'Letter' : 'A4';
  const pos = o.page_number_position || (o.page_numbering && o.page_numbering.position);
  if (pos) out.pageNumbers = pos === 'none' ? 'None' : pos.charAt(0).toUpperCase() + pos.slice(1).replace('_', ' ');
  if (o.margin_preset) out.margins = o.margin_preset === 'custom' ? 'profile' : o.margin_preset;
  else if (o.margins) {
    const m = o.margins, even = m.top_in === m.bottom_in && m.top_in === m.left_in && m.left_in === m.right_in;
    out.margins = (even && { 1: 'normal', 0.5: 'narrow', 1.5: 'wide' }[m.top_in]) || 'profile';
  }
  if (o.heading_size_pt != null && CONFIG.format.options.headingSize.includes(Number(o.heading_size_pt))) out.headingSize = Number(o.heading_size_pt);
  if (o.citations && o.citations.style_override && fmtAppStyle(o.citations.style_override)) out.citationStyle = fmtAppStyle(o.citations.style_override);
  const c = o.cover_page;
  if (c) Object.assign(out, {
    coverPage: !!c.enabled, coverTitle: c.title && c.title !== 'Assignment' ? c.title : '',
    coverStudent: c.student_name || '', coverLecturer: c.lecturer || '', coverCourse: c.course || '', coverDate: c.submission_date || '',
  });
  const t = o.table_of_contents;
  if (t) Object.assign(out, { toc: !!t.enabled, tocDepth: Number(t.max_depth || 3), tocWordField: !!t.field_based });
  const a = o.abbreviations;
  if (a) Object.assign(out, { abbrev: !!a.enabled, abbrevList: Object.entries(a.entries || {}).map(([k, v]) => `${k} — ${v}`).join('\n') });
  if (o.appendices) Object.assign(out, { appendices: !!o.appendices.enabled, appendixLetters: o.appendices.lettered !== false });
  const cap = o.captions;
  if (cap) Object.assign(out, {
    autoCaptions: cap.enabled !== false,
    tableCaption: cap.table_position === 'below' ? 'Below table' : 'Above table',
    figureCaption: cap.figure_position === 'above' ? 'Above figure' : 'Below figure',
  });
  const r = o.references;
  if (r) Object.assign(out, { references: r.enabled !== false, refHeading: r.heading_text || 'References', refNewPage: r.on_new_page !== false, refNumbered: !!r.numbered });
  const sections = o.structure && o.structure.expected_sections;
  if (sections && sections.length) out.requiredSections = sections.join('\n');
  return out;
}

/* Page values -> UserOverrides JSON. Blocks are sent whole (the formatter replaces them),
   typography only when it differs from the style so the profile's own heading styles stay intact. */
function fmtBackendOverrides() {
  const fs = formatState, v = fs.values, changed = new Set(fmtChanged());
  const prof = (BOOT.formatProfiles || {})[fs.styleId] || {};
  const o = { style: fmtBackendStyle(fs.styleId) };
  if (changed.has('font')) o.font_family = v.font;
  if (changed.has('size')) o.font_size_pt = Number(v.size);
  if (changed.has('lineSpacing')) o.line_spacing = parseFloat(v.lineSpacing);
  if (changed.has('alignment')) o.alignment = FMT_ALIGN[v.alignment];
  if (changed.has('firstLineIndent')) o.first_line_indent = !!v.firstLineIndent;
  if (changed.has('pageSize')) o.page_size = v.pageSize.toLowerCase();
  if (changed.has('pageNumbers')) o.page_numbering = { ...(prof.page_numbering || {}), position: v.pageNumbers.toLowerCase().replace(' ', '_') };
  if (changed.has('margins') && FMT_MARGIN_IN[v.margins]) {
    const m = FMT_MARGIN_IN[v.margins];
    o.margins = { top_in: m, bottom_in: m, left_in: m, right_in: m };
  }
  if (v.headingSize !== 'profile') o.heading_size_pt = Number(v.headingSize);
  if (v.citationStyle !== 'same') o.citations = { ...(prof.citations || {}), style_override: fmtBackendStyle(v.citationStyle) };
  const fallbackTitle = fs.mode === 'file' && workDoc.file ? workDoc.file.name.replace(/\.[^.]+$/, '') : 'Assignment';
  const title = v.coverTitle.trim() || (v.coverPage ? fallbackTitle : '');
  o.cover_page = {
    ...(prof.cover_page || {}), enabled: !!v.coverPage, title: title.slice(0, 300),
    student_name: v.coverStudent.trim().slice(0, 150), lecturer: v.coverLecturer.trim().slice(0, 150),
    course: v.coverCourse.trim().slice(0, 200), submission_date: v.coverDate || null,
  };
  o.table_of_contents = { ...(prof.table_of_contents || {}), enabled: !!v.toc, max_depth: Number(v.tocDepth) || 3, field_based: !!v.tocWordField };
  const entries = {};
  v.abbrevList.split('\n').forEach(line => {
    const parts = line.trim().split(/\s*[—–-]\s*|\s*:\s*/);
    if (parts.length > 1 && parts[0].trim() && parts.slice(1).join(' — ').trim()) entries[parts[0].trim()] = parts.slice(1).join(' — ').trim();
  });
  o.abbreviations = { ...(prof.abbreviations || {}), enabled: !!v.abbrev, entries };
  o.appendices = { ...(prof.appendices || {}), enabled: !!v.appendices, lettered: !!v.appendixLetters };
  o.captions = {
    ...(prof.captions || {}), enabled: !!v.autoCaptions,
    table_position: v.tableCaption.startsWith('Above') ? 'above' : 'below',
    figure_position: v.figureCaption.startsWith('Above') ? 'above' : 'below',
  };
  o.references = {
    ...(prof.references || {}), enabled: !!v.references, numbered: !!v.refNumbered, on_new_page: !!v.refNewPage,
    heading_text: v.refHeading.trim() || (prof.references && prof.references.heading_text) || 'References',
  };
  const sections = v.requiredSections.split('\n').map(s => s.trim()).filter(Boolean).slice(0, 30);
  if (sections.length) o.structure = { expected_sections: sections };
  return o;
}

function fmtBriefSummary(styleId, vals) {
  const sections = (vals.requiredSections || '').split('\n').filter(s => s.trim()).length;
  const parts = [
    CONFIG.format.styles.find(s => s.id === styleId).short,
    vals.coverPage && 'cover page',
    vals.toc && `contents (depth ${vals.tocDepth})`,
    sections && `${sections} required section${sections === 1 ? '' : 's'}`,
    vals.font && `${vals.font}${vals.size ? ` ${vals.size} pt` : ''}`,
    vals.lineSpacing && `line spacing ${vals.lineSpacing}`,
    vals.references === false && 'no reference list',
  ].filter(Boolean);
  return parts.join(', ');
}

let formatState = null;   // created on the first visit
const fmtNarrowMQ = window.matchMedia('(max-width: 1100px)');   // preview becomes a drawer
fmtNarrowMQ.addEventListener('change', () => { if (formatState && currentRoute() === 'format') { formatState.previewOpen = false; rerenderFormat(); } });

const fmtStyle = (id) => CONFIG.format.styles.find(s => s.id === (id || formatState.styleId));
const fmtDefaults = () => fmtStyle().defaults;
const fmtGroupKeys = (g) => CONFIG.format.schema[g].flatMap(sec => [sec.toggle, ...sec.fields.map(f => f.key)].filter(Boolean));
// A field is "changed" when it differs from the selected style's default
const fmtChanged = (keys = Object.keys(formatState.values)) => keys.filter(k => String(formatState.values[k]) !== String(fmtDefaults()[k]));
const fmtIsDocx = (f) => !!f && !!f.blob && /\.docx$/i.test(f.name);
const fmtHasDoc = () => (formatState.mode === 'file' ? fmtIsDocx(workDoc.file) : !!workDoc.text.trim());
const fmtDocName = () => (formatState.mode === 'file' && workDoc.file ? workDoc.file.name : 'Pasted text');

function newFormatState() {
  const fromProfile = { Harvard: 'harvard', 'APA 7': 'apa', 'MLA 9': 'mla', Chicago: 'chicago' }[state.profile?.style];
  const styleId = fromProfile || CONFIG.format.defaultStyle;
  return {
    mode: workDocMode('file'),                                 // 1. Document (content lives in workDoc)
    styleTab: 'pick', briefStatus: 'idle',                     // 2. Style (brief text lives in workDoc)
    fillSource: 'brief', prefillBanner: false,                 // where "Filled from …" values came from
    styleId, values: structuredClone(CONFIG.format.styles.find(s => s.id === styleId).defaults),
    fromBrief: [],                                             // keys filled by "Parse brief"
    settingsOpen: false, groupsOpen: { structure: false, appearance: false },   // 3. Settings
    previewPage: 'body', previewOpen: false,                   // preview (previewOpen = mobile drawer)
    status: 'idle', progress: 0, error: '', result: null,     // idle | formatting | done | error
    presets: store.get('format-presets', []), presetFormOpen: false,
  };
}
const fmtState = () => formatState || (formatState = newFormatState());

function fmtOptions(name) {
  if (CONFIG.format.options[name] === 'styles') {
    return [{ value: 'same', label: 'Same as document style' }, ...CONFIG.format.styles.map(s => ({ value: s.id, label: s.label }))];
  }
  return CONFIG.format.options[name].map(o => (typeof o === 'object' ? o : { value: o, label: String(o) }));
}

/* Load a style: every setting takes the style's default, except text the student typed */
function fmtApplyStyle(id, { fromBrief = false } = {}) {
  const fs = formatState, keep = {};
  CONFIG.format.keepOnStyleChange.forEach(k => { if (String(fs.values[k]).trim()) keep[k] = fs.values[k]; });
  fs.styleId = id;
  fs.values = { ...structuredClone(fmtStyle(id).defaults), ...keep };
  fs.fromBrief = fromBrief ? ['styleId'] : fs.fromBrief.filter(k => k in keep && k !== 'styleId');
}

async function fmtParseBrief() {
  const fs = formatState;
  fs.briefStatus = 'parsing';
  rerenderFormat('#fmt-brief');
  const onPage = () => formatState === fs && currentRoute() === 'format';
  try {
    const res = await API.format.parseBrief(workDoc.briefText.trim(), fmtBackendStyle(fs.styleId));
    const vals = fmtFromBackend({ ...(res.overrides || {}), style: res.style || (res.overrides || {}).style });
    const styleId = vals.styleId || fs.styleId;
    delete vals.styleId;
    fmtApplyStyle(styleId, { fromBrief: true });
    Object.assign(fs.values, vals);
    fs.fromBrief = ['styleId', ...Object.keys(vals)];
    fs.briefSummary = fmtBriefSummary(styleId, vals);
    fs.fillSource = 'brief'; fs.prefillBanner = false;
    fs.briefStatus = 'done';
    fs.styleTab = 'pick';
    fs.settingsOpen = true; fs.groupsOpen.structure = true;
    if (onPage()) rerenderFormat('#fmt-brief-result');
    toast('Settings filled from your brief');
  } catch (err) {
    fs.briefStatus = 'idle';
    if (onPage()) rerenderFormat('#fmt-brief');
    toast(err.message || 'Could not read the brief. Try again.');
  }
}

/* ---------- Page ---------- */
function renderFormat() {
  const fs = fmtState(), item = ITEMS.format;
  return `<div class="page fmt-page">
    ${pageHead(item, '<span class="badge">Free</span>', `<button class="btn btn-sm" data-act="start-tour" data-tour-name="format">${icon('help')} How it works</button>`)}
    ${fs.prefillBanner ? `<div class="card fmt-banner" role="status">${icon('check')}<span>Prefilled from Work Review. Change anything you need.</span>
      <button class="icon-btn" data-act="fmt-banner-close" aria-label="Dismiss">${icon('close')}</button></div>` : ''}
    ${fmtStatusHtml()}
    <div class="fmt-layout">
      <div class="fmt-steps">
        ${fmtStepDocument()}
        ${fmtStepStyle()}
        ${fmtStepSettings()}
      </div>
      <aside class="fmt-preview ${fs.previewOpen ? 'open' : ''}" id="fmt-preview" aria-labelledby="fmt-preview-h">
        <div class="fmt-preview-head">
          <h2 id="fmt-preview-h">Preview</h2>
          <span class="small muted">${fmtHasDoc() ? 'Your settings' : 'Sample text'}</span>
          <button class="icon-btn fmt-preview-close" data-act="fmt-preview-close" aria-label="Close preview">${icon('close')}</button>
        </div>
        <div id="fmt-preview-body">${fmtPreviewHtml()}</div>
      </aside>
    </div>
    <div class="fmt-backdrop" data-act="fmt-preview-close" ${fs.previewOpen ? '' : 'hidden'}></div>
    ${fmtBarHtml()}
  </div>`;
}

function fmtStepDocument() {
  const fs = formatState, words = countWords(workDoc.text);
  const seg = (name, legend, value, opts) => `<fieldset class="seg-radios"><legend class="visually-hidden">${legend}</legend>
    ${opts.map(([v, l]) => `<label class="seg-radio"><input type="radio" name="${name}" value="${v}" ${value === v ? 'checked' : ''}>${l}</label>`).join('')}</fieldset>`;
  return `<section class="card fmt-step" id="fmt-step-1" aria-labelledby="fmt-s1">
    <div class="fmt-step-head"><h2 id="fmt-s1"><span class="fmt-num" aria-hidden="true">1</span>Document</h2>
      ${seg('fmt-mode', 'Document source', fs.mode, [['file', 'File'], ['paste', 'Paste text']])}</div>
    ${fs.mode === 'file'
      ? (workDoc.file
        ? `<div class="fmt-file"><span class="file-chip">${icon('file')}<span class="file-name">${esc(workDoc.file.name)}</span><span class="muted small">${fmtSize(workDoc.file.size)}</span>
             <button class="chip-x" data-act="fmt-remove-file" aria-label="Remove ${esc(workDoc.file.name)}">${icon('close')}</button></span>
             ${fmtIsDocx(workDoc.file) ? '' : '<p class="small" style="margin:8px 0 0">Formatting needs a .docx. Upload a .docx or paste your text.</p>'}</div>`
        : `<button type="button" class="dropzone fmt-drop" id="fmt-drop" data-act="fmt-upload">
             ${icon('upload')}<strong>Drop a DOCX or paste your text</strong>
             <span class="small">Click to choose a .docx file · up to ${esc(CONFIG.format.maxFileMb)} MB</span></button>`)
        + '<input type="file" id="fmt-file" accept=".docx" hidden>'
      : `<label class="visually-hidden" for="fmt-text">Your text</label>
         <textarea class="input fmt-text" id="fmt-text" placeholder="Paste your text here…" aria-describedby="fmt-words">${esc(workDoc.text)}</textarea>
         <p class="small muted" id="fmt-words" style="margin:8px 0 0">${fmtNum(words)} words</p>`}
  </section>`;
}

function fmtStepStyle() {
  const fs = formatState;
  const briefBadge = `<span class="tag-brief">${fmtFillLabel()}</span>`;
  const tabs = `<fieldset class="seg-radios"><legend class="visually-hidden">How to choose the style</legend>
    <label class="seg-radio"><input type="radio" name="fmt-style-tab" value="pick" ${fs.styleTab === 'pick' ? 'checked' : ''}>Pick a style</label>
    <label class="seg-radio"><input type="radio" name="fmt-style-tab" value="brief" ${fs.styleTab === 'brief' ? 'checked' : ''}>Auto-fill from brief</label></fieldset>`;
  const pick = `${fs.briefStatus === 'done' ? `<p class="note" id="fmt-brief-result" tabindex="-1">Filled from your brief: ${esc(fs.briefSummary || fmtStyle().short)}. Check the settings below.</p>` : ''}
    <fieldset class="style-cards"><legend class="visually-hidden">Style</legend>
      ${CONFIG.format.styles.map(s => `<label class="style-card">
        <input type="radio" name="fmt-style" value="${s.id}" ${fs.styleId === s.id ? 'checked' : ''}>
        <span class="sc-name">${esc(s.label)}</span><span class="sc-hint">${esc(s.hint)}</span>
        ${fs.styleId === s.id && fs.fromBrief.includes('styleId') ? briefBadge : ''}
      </label>`).join('')}
    </fieldset>`;
  const brief = `<div class="fmt-brief">
      <label class="fld-label" for="fmt-brief">Have a brief from your lecturer? Paste it, we'll fill in the settings</label>
      <textarea class="input fld-textarea" id="fmt-brief" rows="5" placeholder="e.g. Use APA 7. Include a title page and a table of contents…">${esc(workDoc.briefText)}</textarea>
      <div><button class="btn btn-primary" data-act="fmt-parse" id="fmt-parse" ${workDoc.briefText.trim() && fs.briefStatus !== 'parsing' ? '' : 'disabled'}>
        ${fs.briefStatus === 'parsing' ? '<span class="spinner" aria-hidden="true"></span> Reading the brief…' : 'Parse brief'}</button></div>
    </div>`;
  return `<section class="card fmt-step" id="fmt-step-2" aria-labelledby="fmt-s2">
    <div class="fmt-step-head"><h2 id="fmt-s2"><span class="fmt-num" aria-hidden="true">2</span>Style</h2>${tabs}</div>
    ${fs.styleTab === 'pick' ? pick : brief}
  </section>`;
}

function fmtSummaryHtml() {
  const v = formatState.values, n = fmtChanged().length;
  const chips = [fmtStyle().short, `${v.font} ${v.size}`, v.lineSpacing, v.pageSize, v.coverPage && 'Cover page', v.toc && 'Contents', v.references && 'References']
    .filter(Boolean).map(c => `<span class="sum-chip">${esc(c)}</span>`).join('');
  return chips + (n ? `<span class="sum-chip sum-changed"><span class="dot" aria-hidden="true"></span>${n} changed</span>` : '');
}

const fmtFillLabel = () => (formatState.fillSource === 'review' ? 'Filled from Work Review' : 'Filled from brief');

function fmtFieldStatus(key) {
  const fs = formatState, out = [];
  if (fs.fromBrief.includes(key)) out.push(`<span class="tag-brief">${fmtFillLabel()}</span>`);
  if (fmtChanged([key]).length) out.push('<span class="tag-changed"><span class="dot" aria-hidden="true"></span>Changed</span>');
  return out.join('');
}

function fmtFieldHtml(f, { strong = false } = {}) {
  const v = formatState.values[f.key], id = 'fmt-f-' + f.key;
  const hintId = f.hint ? `${id}-hint` : '';
  let control;
  if (f.type === 'switch') {
    control = `<label class="switch-row ${strong ? 'strong' : ''}" for="${id}">
      <input type="checkbox" role="switch" id="${id}" data-fkey="${f.key}" ${v ? 'checked' : ''}>
      <span class="switch" aria-hidden="true"></span><span>${esc(f.label)}</span></label>`;
  } else if (f.type === 'radio') {
    control = `<fieldset class="fld-radios"><legend class="fld-label">${esc(f.label)}</legend><div class="chip-radios">
      ${fmtOptions(f.options).map(o => `<label class="chip-radio"><input type="radio" name="${id}" value="${esc(String(o.value))}" data-fkey="${f.key}" ${String(o.value) === String(v) ? 'checked' : ''}>${esc(o.label)}</label>`).join('')}
      </div></fieldset>`;
  } else if (f.type === 'select') {
    control = `<label class="fld-label" for="${id}">${esc(f.label)}</label>
      <select class="select fld-select" id="${id}" data-fkey="${f.key}" ${hintId ? `aria-describedby="${hintId}"` : ''}>
      ${fmtOptions(f.options).map(o => `<option value="${esc(String(o.value))}" ${String(o.value) === String(v) ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`;
  } else if (f.type === 'textarea') {
    control = `<label class="fld-label" for="${id}">${esc(f.label)}</label>
      <textarea class="input fld-textarea" id="${id}" rows="4" data-fkey="${f.key}" placeholder="${esc(f.placeholder || '')}" ${hintId ? `aria-describedby="${hintId}"` : ''}>${esc(v)}</textarea>`;
  } else {
    control = `<label class="fld-label" for="${id}">${esc(f.label)}</label>
      <input class="input field-input" type="${f.type === 'date' ? 'date' : 'text'}" id="${id}" data-fkey="${f.key}" value="${esc(v)}">`;
  }
  // Citation style: say in words whether it follows the document style
  const extra = f.key === 'citationStyle'
    ? `<p class="fld-hint" id="fmt-cite-note">Citation style: ${v === 'same' ? 'same as document' : esc(fmtStyle(v).label)}</p>` : '';
  return `<div class="fld" data-row="${f.key}">${control}${f.hint ? `<p class="fld-hint" id="${hintId}">${esc(f.hint)}</p>` : ''}${extra}
    <span class="fld-status">${fmtFieldStatus(f.key)}</span></div>`;
}

function fmtGroupHtml(g, title) {
  const fs = formatState, open = fs.groupsOpen[g], n = fmtChanged(fmtGroupKeys(g)).length;
  const sections = CONFIG.format.schema[g].map(sec => {
    const on = !sec.toggle || sec.alwaysShow || fs.values[sec.toggle];
    const titled = !sec.toggle && sec.fields.length > 1;
    return `<section class="fsec" aria-label="${esc(sec.title)}">
      ${sec.toggle ? fmtFieldHtml({ key: sec.toggle, label: sec.toggleLabel || sec.title, type: 'switch' }, { strong: true }) : ''}
      ${titled ? `<h4 class="fsec-title">${esc(sec.title)}</h4>` : ''}
      <div class="fsec-fields ${g === 'appearance' ? 'grid' : ''}" ${sec.toggle && !sec.alwaysShow ? `data-depends="${sec.toggle}"` : ''} ${on ? '' : 'hidden'}>
        ${sec.fields.map(f => fmtFieldHtml(f)).join('')}</div>
    </section>`;
  }).join('');
  return `<div class="fgroup">
    <div class="fgroup-head">
      <button class="fgroup-btn" data-act="fmt-group" data-group="${g}" aria-expanded="${open}" aria-controls="fg-${g}">
        ${icon('chevR')}<span>${title}</span><span class="fgroup-count" id="fg-count-${g}">${n ? `${n} changed` : ''}</span></button>
      <button class="btn btn-sm btn-ghost" data-act="fmt-reset-group" data-group="${g}" id="fg-reset-${g}" ${n ? '' : 'disabled'}>Reset</button>
    </div>
    <div class="fgroup-body" id="fg-${g}" ${open ? '' : 'hidden'}>${sections}</div>
  </div>`;
}

function fmtStepSettings() {
  const fs = formatState;
  const presets = `<div class="fmt-presets">
      ${fs.presets.length ? `<label class="visually-hidden" for="fmt-preset">Apply preset</label>
        <select class="select" id="fmt-preset"><option value="">Apply preset…</option>
          ${fs.presets.map((p, i) => `<option value="${i}">${esc(p.name)}</option>`).join('')}</select>` : ''}
      ${fs.presetFormOpen
        ? `<label class="visually-hidden" for="fmt-preset-name">Preset name</label>
           <input class="input field-input" id="fmt-preset-name" placeholder="Preset name, e.g. My uni APA" style="max-width:220px">
           <button class="btn btn-sm btn-primary" data-act="fmt-preset-save">Save</button>
           <button class="btn btn-sm btn-ghost" data-act="fmt-preset-cancel">Cancel</button>`
        : '<button class="btn btn-sm" data-act="fmt-preset-form">Save as preset</button>'}
    </div>`;
  return `<section class="card fmt-step" id="fmt-step-3" aria-labelledby="fmt-s3">
    <div class="fmt-step-head"><h2 id="fmt-s3"><span class="fmt-num" aria-hidden="true">3</span>Settings <span class="muted small" style="font-weight:400">(optional)</span></h2></div>
    <div class="fmt-summary-row">
      <div class="fmt-summary" id="fmt-summary" aria-label="Current settings">${fmtSummaryHtml()}</div>
      <button class="btn btn-sm" data-act="fmt-settings" aria-expanded="${fs.settingsOpen}" aria-controls="fmt-panel">${fs.settingsOpen ? 'Hide settings' : 'Edit settings'}</button>
    </div>
    <div class="fmt-panel" id="fmt-panel" ${fs.settingsOpen ? '' : 'hidden'}>
      <div class="fmt-panel-top">
        <p class="small muted" style="margin:0">Settings come from the selected style. Change only what you need.</p>
        <button class="btn btn-sm btn-ghost" data-act="fmt-reset-all" id="fmt-reset-all" ${fmtChanged().length ? '' : 'disabled'}>Reset all</button>
      </div>
      ${fmtGroupHtml('structure', 'Structure')}
      ${fmtGroupHtml('appearance', 'Appearance')}
      ${presets}
    </div>
  </section>`;
}

/* ---------- Live preview ---------- */
function fmtPages() {
  const v = formatState.values;
  return [v.coverPage && 'cover', (v.toc || v.abbrev) && 'toc', 'body', v.references && 'refs'].filter(Boolean);
}

function fmtPreviewHtml() {
  const fs = formatState, v = fs.values, st = fmtStyle(), pages = fmtPages();
  if (!pages.includes(fs.previewPage)) fs.previewPage = 'body';
  const page = fs.previewPage, pageNo = pages.indexOf(page) + 1;
  const labels = { cover: 'Cover', toc: 'Contents', body: 'Text', refs: v.refHeading || 'References' };
  const margin = { normal: 1, narrow: 0.5, wide: 1.5, profile: st.profileMarginIn }[v.margins];
  const heading = v.headingSize === 'profile' ? st.profileHeadingPt : v.headingSize;
  const align = { Left: 'left', Justified: 'justify', Center: 'center', Right: 'right' }[v.alignment];
  const style = `--pw:${v.pageSize === 'Letter' ? 8.5 : 8.27};--ph:${v.pageSize === 'Letter' ? 11 : 11.69};--m:${margin};--fs:${v.size};--hs:${heading};--lh:${parseFloat(v.lineSpacing) * 1.15};font-family:${CONFIG.format.fontStacks[v.font]};text-align:${align}`;
  const secs = v.requiredSections.split('\n').map(s => s.trim()).filter(Boolean);
  const titles = secs.length ? secs : ['Introduction', 'Background', 'Discussion', 'Conclusion'];
  const paras = fs.mode === 'paste' && workDoc.text.trim()
    ? workDoc.text.split(/\n\s*\n|\n/).map(p => p.trim()).filter(Boolean).slice(0, 3)
    : CONFIG.format.sampleParagraphs;
  const ph = (val, label) => (val.trim() ? esc(val) : `<span class="pv-ph">[${label}]</span>`);
  const cite = v.citationStyle === 'same' ? fs.styleId : v.citationStyle;
  const cap = (kind, n, text) => `<p class="pv-cap">${kind}${v.autoCaptions ? ` ${n}` : ''}. ${text}</p>`;
  let content = '';
  if (page === 'cover') {
    const date = v.coverDate ? new Date(v.coverDate + 'T12:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '';
    content = `<div class="pv-cover"><p class="pv-cover-title">${ph(v.coverTitle, 'Title')}</p>
      <p>${ph(v.coverStudent, 'Student')}</p><p>${ph(v.coverLecturer, 'Lecturer')}</p><p>${ph(v.coverCourse, 'Course')}</p><p>${date ? esc(date) : ph('', 'Submission date')}</p></div>`;
  } else if (page === 'toc') {
    const rows = [];
    titles.forEach((t, i) => {
      rows.push([1, `${i + 1}. ${t}`, 3 + i]);
      if (i < 2) {
        if (v.tocDepth >= 2) rows.push([2, `${i + 1}.1 Key points`, 3 + i]);
        if (v.tocDepth >= 3) rows.push([3, `${i + 1}.1.1 Details`, 3 + i]);
        if (v.tocDepth >= 4) rows.push([4, `${i + 1}.1.1.1 Example`, 3 + i]);
      }
    });
    if (v.references) rows.push([1, v.refHeading || 'References', 3 + titles.length]);
    if (v.appendices) ['A', 'B'].forEach((l, i) => rows.push([1, `Appendix ${v.appendixLetters ? l : i + 1}`, 4 + titles.length + i]));
    const abbr = v.abbrevList.split('\n').map(s => s.trim()).filter(Boolean);
    content = (v.toc ? `<p class="pv-h">Contents</p>
        <p class="pv-note">${v.tocWordField ? 'Word TOC field: updates in Word' : 'Static list'}</p>
        <div class="pv-toc">${rows.map(([lvl, t, p]) => `<div class="pv-toc-row" style="padding-left:${(lvl - 1) * 1.2}em"><span>${esc(t)}</span><span class="pv-dots"></span><span>${p}</span></div>`).join('')}</div>` : '')
      + (v.abbrev ? `<p class="pv-h">List of abbreviations</p>${(abbr.length ? abbr : ['[CODE — meaning]']).map(a => `<p class="pv-abbr">${esc(a)}</p>`).join('')}` : '');
  } else if (page === 'body') {
    const figure = `<div class="pv-fig">${v.figureCaption === 'Above figure' ? cap('Figure', 1, 'Weekly study hours by year') : ''}
      <div class="pv-fig-box" aria-hidden="true"></div>${v.figureCaption === 'Below figure' ? cap('Figure', 1, 'Weekly study hours by year') : ''}</div>`;
    const table = `<div class="pv-fig">${v.tableCaption === 'Above table' ? cap('Table', 1, 'Survey responses by group') : ''}
      <table class="pv-table"><tr><th>Group</th><th>Hours</th></tr><tr><td>Year 1</td><td>12</td></tr></table>${v.tableCaption === 'Below table' ? cap('Table', 1, 'Survey responses by group') : ''}</div>`;
    content = `<p class="pv-h">1. ${esc(titles[0])}</p><p>${esc(paras[0])}</p>${paras[1] ? `<p>${esc(paras[1])}</p>` : ''}${figure}
      <p class="pv-h">2. ${esc(titles[1] || 'Background')}</p><p>${esc(paras[2] || paras[0])}</p>${table}`;
  } else {
    const refs = CONFIG.format.sampleRefs[cite];
    content = `${v.refNewPage ? '' : `<p>${esc(paras[0])}</p>`}
      <p class="pv-h">${esc(v.refHeading || 'References')}</p>
      ${v.refNumbered ? `<ol class="pv-refs-num">${refs.map(r => `<li>${esc(r)}</li>`).join('')}</ol>`
        : refs.map(r => `<p class="pv-ref">${esc(r)}</p>`).join('')}
      <p class="pv-note">${v.refNewPage ? 'Starts on a new page' : 'Continues after the last section'} · Citation style: ${esc(fmtStyle(cite).label)}</p>`;
  }
  const num = v.pageNumbers !== 'None' && page !== 'cover'
    ? `<span class="pv-num pv-${v.pageNumbers.toLowerCase().replace(' ', '-')}">${pageNo}</span>` : '';
  const tabs = pages.length > 1 ? `<div class="pv-tabs" role="group" aria-label="Preview page">${pages.map(p =>
    `<button class="sl-filter" data-act="fmt-page" data-page="${p}" aria-pressed="${p === page}">${esc(labels[p])}</button>`).join('')}</div>` : '';
  return `${tabs}<div class="pv-page" style="${esc(style)}" role="group" aria-label="Preview: ${esc(labels[page])} page, ${esc(v.pageSize)}">
    <div class="pv-in ${v.firstLineIndent ? 'pv-indent' : ''}">${content}</div>${num}</div>
    <p class="small muted" style="margin:8px 0 0">${esc(v.pageSize)} · ${esc(v.font)} ${v.size} pt · line spacing ${esc(v.lineSpacing)} · ${esc(v.alignment)}</p>`;
}

/* ---------- Status + bottom bar ---------- */
function fmtStatusHtml() {
  const fs = formatState;
  if (fs.status === 'formatting') return `<section class="card fmt-status" aria-live="polite">
      <h2 id="fmt-status-h" tabindex="-1">Formatting your document…</h2>
      <div class="fmt-progress" role="progressbar" aria-label="Formatting progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${fs.progress}"><span style="width:${fs.progress}%"></span></div>
      <p class="small muted" id="fmt-progress-text" style="margin:8px 0 0">${fs.progress}% · ${esc(fmtStyle().label)}</p></section>`;
  if (fs.status === 'done') return `<section class="card fmt-status done" aria-live="polite">
      <h2 id="fmt-status-h" tabindex="-1">${icon('check')} Your document is ready</h2>
      <p class="muted" style="margin:0">${esc(fmtDocName())} · ${esc(fmtStyle().label)}${fmtChanged().length ? ` · ${fmtChanged().length} custom settings` : ''}</p>
      ${fs.result && fs.result.notices.length ? `<ul class="small muted fmt-notices">${fs.result.notices.slice(0, 5).map(n => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}
      <div class="fmt-status-actions">
        <button class="btn btn-primary" data-act="fmt-download">${icon('download')} Download .docx</button>
        <button class="btn" data-act="fmt-another">Format another</button>
        <button class="btn" data-act="fmt-recheck">${icon('clipboard')} Check result again</button>
        <a href="#/check">Check result in Work Review</a>
      </div></section>`;
  if (fs.status === 'error') return `<section class="card fmt-status error" role="alert">
      <h2 id="fmt-status-h" tabindex="-1">Formatting failed. Try again.</h2>
      <p class="muted" style="margin:0">${fs.error ? `${esc(fs.error)} ` : ''}Your document and settings are kept.</p>
      <div class="fmt-status-actions"><button class="btn btn-primary" data-act="fmt-run">Try again</button></div></section>`;
  return '';
}

function fmtBarHtml() {
  const fs = formatState, ready = fmtHasDoc(), busy = fs.status === 'formatting';
  return `<div class="fmt-bar" id="fmt-bar">
    <button class="btn fmt-preview-btn" data-act="fmt-preview-open" aria-controls="fmt-preview" aria-expanded="${fs.previewOpen}">Preview</button>
    <span class="fmt-free"><span class="badge">Free</span><span class="small muted">Formatting and Work Review are free</span></span>
    <span class="spacer"></span>
    <span class="small muted" id="fmt-hint" ${ready ? 'hidden' : ''}>Add a document first</span>
    <button class="btn btn-primary btn-lg" data-act="fmt-run" id="fmt-run" ${ready && !busy ? '' : 'disabled'} ${ready ? '' : 'aria-describedby="fmt-hint"'}>
      ${busy ? '<span class="spinner" aria-hidden="true"></span> Formatting…' : 'Format document'}</button>
  </div>`;
}

/* Update everything that depends on the settings, without re-rendering the inputs (keeps focus) */
function fmtRefresh() {
  const fs = formatState;
  $$('[data-row]').forEach(r => { const st = r.querySelector('.fld-status'), html = fmtFieldStatus(r.dataset.row); if (st.innerHTML !== html) st.innerHTML = html; });
  ['structure', 'appearance'].forEach(g => {
    const n = fmtChanged(fmtGroupKeys(g)).length;
    $('#fg-count-' + g).textContent = n ? `${n} changed` : '';
    $('#fg-reset-' + g).disabled = !n;
  });
  $('#fmt-reset-all').disabled = !fmtChanged().length;
  $$('[data-depends]').forEach(el => { el.hidden = !fs.values[el.dataset.depends]; });
  $('#fmt-summary').innerHTML = fmtSummaryHtml();
  const note = $('#fmt-cite-note');
  if (note) note.textContent = `Citation style: ${fs.values.citationStyle === 'same' ? 'same as document' : fmtStyle(fs.values.citationStyle).label}`;
  $('#fmt-preview-body').innerHTML = fmtPreviewHtml();
  const ready = fmtHasDoc();
  $('#fmt-run').disabled = !ready || fs.status === 'formatting';
  $('#fmt-hint').hidden = ready;
  if (ready) $('#fmt-run').removeAttribute('aria-describedby'); else $('#fmt-run').setAttribute('aria-describedby', 'fmt-hint');
}

function rerenderFormat(focusSel) {
  const y = window.scrollY;
  $('#main').innerHTML = renderFormat();
  bindFormat();
  window.scrollTo(0, y);
  if (focusSel) $(focusSel)?.focus({ preventScroll: true });
}

function fmtSetPreviewOpen(open) {
  const fs = formatState;
  fs.previewOpen = open;
  $('#fmt-preview').classList.toggle('open', open);
  $('.fmt-backdrop').hidden = !open;
  $('.fmt-preview-btn').setAttribute('aria-expanded', String(open));
  $('#fmt-preview').inert = fmtNarrowMQ.matches && !open;
  (open ? $('.fmt-preview-close') : $('.fmt-preview-btn'))?.focus();
}

function bindFormat() {
  const fs = formatState;
  $('#fmt-preview').inert = fmtNarrowMQ.matches && !fs.previewOpen;
  // Settings fields
  $$('#main [data-fkey]').forEach(el => {
    const live = el.tagName === 'TEXTAREA' || el.type === 'text' || el.type === 'date';
    el.addEventListener(live ? 'input' : 'change', () => {
      const key = el.dataset.fkey;
      let val = el.type === 'checkbox' ? el.checked : el.value;
      if (CONFIG.format.numericFields.includes(key) && /^\d+$/.test(val)) val = Number(val);
      fs.values[key] = val;
      fs.fromBrief = fs.fromBrief.filter(k => k !== key);   // the student changed it by hand
      fmtRefresh();
    });
  });
  // Document source, style tab and style cards
  $$('input[name="fmt-mode"]').forEach(r => r.addEventListener('change', () => { fs.mode = r.value; rerenderFormat(`input[name="fmt-mode"][value="${r.value}"]`); }));
  $$('input[name="fmt-style-tab"]').forEach(r => r.addEventListener('change', () => { fs.styleTab = r.value; rerenderFormat(`input[name="fmt-style-tab"][value="${r.value}"]`); }));
  $$('input[name="fmt-style"]').forEach(r => r.addEventListener('change', () => {
    fmtApplyStyle(r.value);
    rerenderFormat(`input[name="fmt-style"][value="${r.value}"]`);
  }));
  const text = $('#fmt-text');
  if (text) text.addEventListener('input', () => { workDoc.text = text.value; workDoc.formatted = null; $('#fmt-words').textContent = `${fmtNum(countWords(workDoc.text))} words`; fmtRefresh(); });
  const brief = $('#fmt-brief');
  if (brief) brief.addEventListener('input', () => { workDoc.briefText = brief.value; $('#fmt-parse').disabled = !workDoc.briefText.trim(); });
  // File: click or drag and drop (.docx only)
  const input = $('#fmt-file'), drop = $('#fmt-drop');
  const take = (file) => {
    if (!file) return;
    if (!/\.docx$/i.test(file.name)) { toast('Please choose a .docx file, or paste your text'); return; }
    if (file.size > Number(CONFIG.format.maxFileMb) * 1024 * 1024) { toast(`The file is larger than ${CONFIG.format.maxFileMb} MB`); return; }
    workDoc.file = { name: file.name, size: file.size, blob: file }; workDoc.formatted = null;
    rerenderFormat('[data-act="fmt-remove-file"]');
  };
  if (input) input.addEventListener('change', () => take(input.files[0]));
  if (drop) {
    drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('drag'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
    drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('drag'); take(e.dataTransfer.files[0]); });
  }
  // Presets
  $('#fmt-preset')?.addEventListener('change', (e) => {
    const p = fs.presets[Number(e.target.value)];
    if (!p) return;
    fs.styleId = p.styleId; fs.values = structuredClone(p.values); fs.fromBrief = [];
    rerenderFormat('#fmt-preset');
    toast(`Preset “${p.name}” applied`);
  });
  $('#fmt-preset-name')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); fmtSavePreset(); } });
}

function fmtSavePreset() {
  const fs = formatState, name = $('#fmt-preset-name').value.trim();
  if (!name) { $('#fmt-preset-name').focus(); toast('Give the preset a name'); return; }
  fs.presets.push({ name, styleId: fs.styleId, values: structuredClone(fs.values) });
  store.set('format-presets', fs.presets);
  fs.presetFormOpen = false;
  rerenderFormat('#fmt-preset');
  toast(`Preset “${name}” saved`);
}

async function fmtRun() {
  const fs = formatState;
  if (!fmtHasDoc() || fs.status === 'formatting') return;
  if (CONFIG.format.guestNeedsSignup && !state.signedIn) {
    return openSignup({ intent: 'format', title: 'Create your free account', lead: `Register to continue. You get ${CONFIG.signupCredits} free credits.` });
  }
  fs.status = 'formatting'; fs.progress = 0; fs.error = ''; fs.result = null;
  rerenderFormat('#fmt-status-h');
  window.scrollTo({ top: 0, behavior: 'smooth' });
  // The request gives no progress events: creep towards 90% and finish on the response
  const timer = setInterval(() => {
    if (formatState !== fs || fs.status !== 'formatting') { clearInterval(timer); return; }
    fs.progress = Math.min(90, fs.progress + Math.max(1, Math.round((90 - fs.progress) / 8)));
    const bar = $('.fmt-progress');
    if (bar) {
      bar.setAttribute('aria-valuenow', fs.progress); bar.firstElementChild.style.width = fs.progress + '%';
      $('#fmt-progress-text').textContent = `${fs.progress}% · ${fmtStyle().label}`;
    }
  }, 400);
  try {
    const res = await API.format.run({
      file: fs.mode === 'file' ? workDoc.file.blob : null,
      text: fs.mode === 'paste' ? workDoc.text : '',
      style: fmtBackendStyle(fs.styleId),
      overrides: fmtBackendOverrides(),
    });
    fs.status = 'done'; fs.progress = 100;
    fs.result = {
      id: res.document_id,
      fileName: `${fmtDocName().replace(/\.docx$/i, '')} (${fmtStyle().short}).docx`,
      notices: (res.notices || []).map(n => n.message).filter(Boolean),
    };
    const today = new Date().toISOString().slice(0, 10);
    state.docs.unshift({ id: 'd' + Date.now(), title: `${fmtDocName()} (${fmtStyle().short})`, tool: 'format', date: today });
    saveDocs();
  } catch (err) {
    fs.status = 'error';
    fs.error = err.message || '';
  } finally {
    clearInterval(timer);
  }
  if (formatState === fs && currentRoute() === 'format') rerenderFormat('#fmt-status-h');
}

/* Work Review checks the formatted file, not the original */
async function fmtRecheck(btn) {
  const fs = formatState, r = fs.result;
  if (!r) return;
  btn.disabled = true;
  try {
    const blob = await API.format.download(r.id);
    const file = new File([blob], r.fileName, { type: blob.type });
    workDoc.file = { name: file.name, size: file.size, blob: file };
    workDoc.formatted = { styleId: fs.styleId };
    Object.assign(reviewState(), { docMode: 'file', autoRun: true });
    go('check');
  } catch (err) {
    btn.disabled = false;
    toast(err.message || 'Could not open the formatted file. Try again.');
  }
}

async function fmtDownload(btn) {
  const r = formatState.result;
  if (!r) return;
  btn.disabled = true;
  try {
    const blob = await API.format.download(r.id);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = r.fileName;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  } catch (err) {
    toast(err.message || 'Download failed. Try again.');
  } finally {
    btn.disabled = false;
  }
}

function fmtAction(act, el) {
  const fs = formatState;
  switch (act) {
    case 'fmt-upload': $('#fmt-file').click(); break;
    case 'fmt-remove-file': workDoc.file = null; workDoc.formatted = null; rerenderFormat('#fmt-drop'); break;
    case 'fmt-parse': fmtParseBrief(); break;
    case 'fmt-settings': fs.settingsOpen = !fs.settingsOpen; rerenderFormat('[data-act="fmt-settings"]'); break;
    case 'fmt-group': fs.groupsOpen[el.dataset.group] = !fs.groupsOpen[el.dataset.group]; rerenderFormat(`[data-act="fmt-group"][data-group="${el.dataset.group}"]`); break;
    case 'fmt-reset-group': case 'fmt-reset-all': {
      const keys = act === 'fmt-reset-all' ? Object.keys(fs.values) : fmtGroupKeys(el.dataset.group);
      keys.forEach(k => { fs.values[k] = structuredClone(fmtDefaults()[k]); });
      fs.fromBrief = fs.fromBrief.filter(k => !keys.includes(k));
      rerenderFormat(act === 'fmt-reset-all' ? '[data-act="fmt-settings"]' : `[data-act="fmt-group"][data-group="${el.dataset.group}"]`);
      toast(act === 'fmt-reset-all' ? `All settings reset to ${fmtStyle().short}` : `${el.dataset.group === 'structure' ? 'Structure' : 'Appearance'} reset to ${fmtStyle().short}`);
      break;
    }
    case 'fmt-page': fs.previewPage = el.dataset.page; $('#fmt-preview-body').innerHTML = fmtPreviewHtml(); $(`[data-act="fmt-page"][data-page="${fs.previewPage}"]`)?.focus(); break;
    case 'fmt-run': fmtRun(); break;
    case 'fmt-download': fmtDownload(el); break;
    case 'fmt-another': Object.assign(workDoc, { file: null, text: '', formatted: null }); Object.assign(fs, { status: 'idle', progress: 0, result: null }); rerenderFormat('#fmt-drop'); window.scrollTo(0, 0); break;
    case 'fmt-recheck': fmtRecheck(el); break;
    case 'fmt-banner-close': fs.prefillBanner = false; rerenderFormat('#fmt-s1'); break;
    case 'fmt-preview-open': fmtSetPreviewOpen(true); break;
    case 'fmt-preview-close': fmtSetPreviewOpen(false); break;
    case 'fmt-preset-form': fs.presetFormOpen = true; rerenderFormat('#fmt-preset-name'); break;
    case 'fmt-preset-cancel': fs.presetFormOpen = false; rerenderFormat('[data-act="fmt-preset-form"]'); break;
    case 'fmt-preset-save': fmtSavePreset(); break;
  }
}

/* =========================================================
   Work Review: how well the work meets the task.
   Left: Your work (document, brief, type). Right: Results (score, checklist, action plan).
   Document and brief live in workDoc, shared with Formatting.
   ========================================================= */
let _review = null;
const reviewState = () => _review || (_review = {
  docMode: workDocMode('paste'), briefMode: workDoc.briefFile ? 'file' : 'paste',
  docType: 'Essay', status: 'idle', result: null, autoRun: false,
  reqs: null, reqTimer: 0,   // requirements read from the brief: { key, status, parsed, text, promise }
});
const rvHasDoc = () => (reviewState().docMode === 'file' ? !!workDoc.file?.blob : !!workDoc.text.trim());
const rvDocName = () => (reviewState().docMode === 'file' && workDoc.file ? workDoc.file.name : 'Pasted text');
const rvVerdict = (score) => CONFIG.review.verdicts.find(v => score >= v.min).text;

/* ---------- Brief → requirements (/api/extract-requirements) ---------- */
function rvBriefSource() {
  const rs = reviewState(), file = workDoc.briefFile?.blob ? workDoc.briefFile : null, text = workDoc.briefText.trim();
  if (rs.briefMode === 'file' && file) return { key: `file:${file.name}:${file.size}`, file: file.blob };
  if (text) return { key: `text:${text}`, text };
  if (file) return { key: `file:${file.name}:${file.size}`, file: file.blob };
  return null;
}

function rvDetectReqs() {
  const rs = reviewState(), src = rvBriefSource();
  clearTimeout(rs.reqTimer);
  rs.reqTimer = 0;
  if (!src) { rs.reqs = null; return Promise.resolve(null); }
  if (rs.reqs && rs.reqs.key === src.key) return rs.reqs.promise;
  const reqs = { key: src.key, status: 'loading' };
  reqs.promise = API.review.requirements({ text: src.text, file: src.file })
    .then(d => {
      const { gemini_diagnostics, ai_provider, ...parsed } = d.requirements || {};
      return Object.assign(reqs, { status: 'done', parsed, text: d.source_text || src.text || '' });
    })
    .catch(err => Object.assign(reqs, { status: 'error', error: err.message || 'Could not read the brief.' }))
    .finally(() => { if (reviewState().reqs === reqs && currentRoute() === 'check') rvRefreshReqs(); });
  rs.reqs = reqs;
  rvRefreshReqs();
  return reqs.promise;
}

/* What the brief asks for, as short lines for "Detected requirements" */
function rvStyleName(style, text) {
  if (!/^(APA|MLA|Chicago)$/i.test(style || '')) return style;
  const ed = new RegExp(`\\b${style}\\s*\\(?(\\d{1,2})(?:st|nd|rd|th)?\\b`, 'i').exec(text || '');
  return ed ? `${style} ${ed[1]}` : style;
}

function rvReqLines(p, text) {
  if (!p) return [];
  const spacing = Number(p.spacing || p.line_spacing);
  return [
    p.word_count && `Word count: ${p.word_count}`,
    p.citation_style && `Referencing: ${rvStyleName(p.citation_style, text)}`,
    ...(p.required_sections || []).map(s => `Required section: ${s}`),
    p.cover_page_required && 'Cover page',
    spacing && (spacing === 2 ? 'Double line spacing' : `Line spacing ${spacing}`),
    (p.font_family || p.font_size) && [p.font_family, p.font_size && `${p.font_size} pt`].filter(Boolean).join(' '),
    p.margins && `Margins: ${p.margins}`,
    p.page_numbers_required && 'Page numbers',
    p.submission_format && `Submit as ${p.submission_format}`,
  ].filter(Boolean);
}

function rvReqsHtml() {
  const rs = reviewState();
  if (!rs.reqs || rs.reqs.status === 'loading') {
    return '<div class="loading small"><span class="spinner" aria-hidden="true"></span> Reading the brief…</div>';
  }
  if (rs.reqs.status === 'error') return `<p class="small muted" style="margin:0">${esc(rs.reqs.error)}</p>`;
  const lines = rvReqLines(rs.reqs.parsed, rs.reqs.text);
  if (!lines.length) return '<p class="small muted" style="margin:0">No specific requirements found in the brief. We’ll still check the text.</p>';
  return `<ul>${lines.map(q => `<li>${icon('check')}${esc(q)}</li>`).join('')}</ul>
    <button class="btn btn-sm" data-act="rv-use-reqs">${icon('align')} Use these requirements in Formatting</button>`;
}

function rvRefreshReqs() {
  const el = $('#rv-reqs-body');
  if (el) el.innerHTML = rvReqsHtml();
}

/* ---------- /api/check-document → results ---------- */
const RV_STATUS = { PASS: 'met', PARTIAL: 'partly', FAIL: 'missing' };
const RV_CATEGORY = {
  formatting: 'Formatting', structure: 'Structure', references: 'References and citations',
  requirements_match: 'Brief requirements', clarity_organization: 'Clarity of organization',
};

function rvFormatRules(rules) {
  return rules.map(r => {
    const name = r.item.charAt(0).toUpperCase() + r.item.slice(1);
    if (r.ok === null) return `${name}: not checked`;
    if (r.required === 'Required') return `${name}: ${r.ok ? 'found' : 'missing'}`;
    return r.ok ? `${name}: ${r.detected}` : `${name}: ${r.required} required, found ${r.detected}`;
  }).join(' · ');
}

function rvMapResult(d, full) {
  const vals = d.validations || [];
  const items = vals.map(v => {
    const status = RV_STATUS[v.status] || 'notChecked';
    const rules = v.id === 'formatting' && v.details && v.details.items;
    const reason = status === 'notChecked'
      ? (v.fix || v.detected || 'Not enough information to check this.')
      : rules ? rvFormatRules(rules)
      : [v.required && `Required: ${v.required}`, v.detected && `Found: ${v.detected}`].filter(Boolean).join(' · ') || v.fix || '';
    return { label: v.label, status, reason };
  });
  (d.not_checked || []).forEach(n => items.push({
    label: RV_CATEGORY[n.category] || n.category,
    status: 'notChecked',
    reason: /docx/i.test(n.reason || '') ? 'Upload the .docx file to check formatting.' : 'Not enough information to check this.',
  }));
  items.push({ label: 'Risk of AI-written passages', status: 'notChecked', reason: `Run ${ITEMS.turnitin.label} to see which passages look AI-written.` });

  // Action plan: the checker's steps in order, formatting fixes merged into one step
  const byLabel = Object.fromEntries(vals.map(v => [v.label, v]));
  const plan = [], fmtFixes = [];
  (d.action_plan || []).forEach(step => {
    const v = byLabel[step.title] || {};
    if (v.category === 'formatting') { fmtFixes.push(step.action); return; }
    const missing = (v.details && v.details.missing) || [];
    plan.push({ text: step.action, act: 'rv-editor', section: v.id === 'sections' ? missing.join('|') : '', btn: 'Open in Editor', icon: 'file' });
  });
  if (fmtFixes.length) plan.unshift({ text: `Fix formatting: ${fmtFixes.join(' ')}`, act: 'rv-fix-format', btn: 'Fix formatting', icon: 'align' });
  plan.push({ text: 'Check which passages look AI-written', act: 'rv-ai', btn: `Open ${ITEMS.turnitin.label}`, icon: 'scan' });

  return { full, score: Math.round(d.score || 0), items, plan, docType: reviewState().docType };
}

function rvActionPlan(result) {
  if (result.plan) return result.plan;
  const open = result.items.filter(i => i.action && (i.status === 'partly' || i.status === 'missing'));
  const plan = [];
  const fmt = open.filter(i => i.action === 'format');
  if (fmt.length) plan.push({ text: `Fix formatting: ${fmt.map(i => i.fix).join(', ')}`, act: 'rv-fix-format', btn: 'Fix formatting', icon: 'align' });
  open.filter(i => i.action === 'editor').forEach(i => plan.push({ text: i.fix, act: 'rv-editor', section: i.section || '', btn: 'Open in Editor', icon: 'file' }));
  open.filter(i => i.action === 'ai').forEach(i => plan.push({ text: i.fix, act: 'rv-ai', btn: `Open ${ITEMS.turnitin.label}`, icon: 'scan' }));
  return plan;
}

function rvStatusHtml(status) {
  const st = CONFIG.review.statuses[status];
  return `<span class="rv-status rv-${status}">${icon(st.icon)}${st.label}</span>`;
}

function rvResultHtml(r, { example = false } = {}) {
  const R = CONFIG.review, checked = r.items.filter(i => i.status !== 'notChecked'), notChecked = r.items.filter(i => i.status === 'notChecked');
  const plan = rvActionPlan(r);
  const delta = !example && r.before != null && r.before !== r.score
    ? `<span class="rv-delta">${r.before} → ${r.score}<span class="small"> after formatting</span></span>` : '';
  return `<div class="rv-mode">
      ${r.full ? '<span class="tag-brief">Full check against your brief</span>'
        : `<span class="tag-changed">Basic check</span>${example ? '' : '<button class="link-btn small" data-act="rv-add-brief">Add a brief for a full check</button>'}`}
      <span class="small muted">${esc(r.docType)}</span>
    </div>
    <div class="rv-score">
      <div class="rv-score-num"><b>${r.score}</b><span>/100</span></div>
      <div><p class="rv-verdict">${esc(rvVerdict(r.score))}</p>${delta}
        <p class="small muted" style="margin:4px 0 0">${esc(R.disclaimer)}</p></div>
    </div>
    <div class="meter-bar rv-bar"><span style="width:${r.score}%"></span></div>
    <h3 class="rv-h">Requirements</h3>
    <ul class="rv-list">${checked.map(i => `<li class="rv-item">${rvStatusHtml(i.status)}
      <div><b>${esc(i.label)}</b><p class="small muted">${esc(i.reason)}</p></div></li>`).join('')}</ul>
    ${plan.length ? `<h3 class="rv-h">Action plan</h3>
      <ol class="rv-plan">${plan.map(p => `<li><span>${esc(p.text)}</span>
        ${example ? '' : `<button class="btn btn-sm" data-act="${p.act}" data-section="${esc(p.section || '')}">${icon(p.icon)} ${esc(p.btn)}</button>`}</li>`).join('')}</ol>` : ''}
    ${notChecked.length ? `<details class="rv-notchecked"><summary>Not checked (${notChecked.length})</summary>
      <ul class="rv-list">${notChecked.map(i => `<li class="rv-item">${rvStatusHtml('notChecked')}
        <div><b>${esc(i.label)}</b><p class="small muted">${esc(i.reason)}</p></div></li>`).join('')}</ul></details>` : ''}`;
}

function renderReview() {
  const rs = reviewState(), item = ITEMS.check, R = CONFIG.review;
  const hasBrief = workDocHasBrief();
  const seg = (name, legend, value, opts) => `<fieldset class="seg-radios"><legend class="visually-hidden">${legend}</legend>
    ${opts.map(([v, l]) => `<label class="seg-radio"><input type="radio" name="${name}" value="${v}" ${value === v ? 'checked' : ''}>${l}</label>`).join('')}</fieldset>`;
  const fileChip = (f, act) => `<span class="file-chip">${icon('file')}<span class="file-name">${esc(f.name)}</span><span class="muted small">${fmtSize(f.size)}</span>
    <button class="chip-x" data-act="${act}" aria-label="Remove ${esc(f.name)}">${icon('close')}</button></span>`;
  const drop = (id, act, label) => `<button type="button" class="dropzone rv-drop" id="${id}" data-act="${act}">${icon('upload')}<strong>${label}</strong><span class="small">.docx or .pdf</span></button>`;

  const docBlock = rs.docMode === 'file'
    ? (workDoc.file ? `<div>${fileChip(workDoc.file, 'rv-remove-doc')}${workDoc.formatted ? `<p class="small muted" style="margin:8px 0 0">Formatted in ${esc(fmtStyle(workDoc.formatted.styleId).label)}</p>` : ''}</div>`
      : drop('rv-doc-drop', 'rv-upload-doc', 'Upload your document'))
    : `<label class="visually-hidden" for="rv-doc-text">Your text</label>
       <textarea class="input rv-text" id="rv-doc-text" placeholder="Paste your work here…" aria-describedby="rv-doc-words">${esc(workDoc.text)}</textarea>
       <p class="small muted" id="rv-doc-words" style="margin:0">${fmtNum(countWords(workDoc.text))} words${workDoc.formatted ? ` · formatted in ${esc(fmtStyle(workDoc.formatted.styleId).label)}` : ''}</p>`;
  const briefBlock = rs.briefMode === 'file'
    ? (workDoc.briefFile ? `<div>${fileChip(workDoc.briefFile, 'rv-remove-brief')}</div>` : drop('rv-brief-drop', 'rv-upload-brief', 'Upload the brief'))
    : `<label class="visually-hidden" for="rv-brief-text">Brief</label>
       <textarea class="input fld-textarea" id="rv-brief-text" rows="4" placeholder="Paste the task from your lecturer: requirements, word count, style…">${esc(workDoc.briefText)}</textarea>`;

  return `<div class="page rv-page">
    ${pageHead(item, '<span class="badge">Free</span>', `<button class="btn btn-sm" data-act="start-tour" data-tour-name="review">${icon('help')} How it works</button>`)}
    <div class="rv-layout">
      <section class="rv-col" aria-labelledby="rv-work-h">
        <h2 id="rv-work-h">Your work</h2>
        <div class="card rv-block" id="rv-doc">
          <div class="fmt-step-head"><h3>Document</h3>${seg('rv-doc-mode', 'Document source', rs.docMode, [['paste', 'Paste text'], ['file', 'Upload']])}</div>
          ${docBlock}
          <input type="file" id="rv-doc-file" accept=".docx,.pdf" hidden>
        </div>
        <div class="card rv-block" id="rv-brief">
          <div class="fmt-step-head"><h3>Brief <span class="muted small" style="font-weight:400">(optional)</span></h3>${seg('rv-brief-mode', 'Brief source', rs.briefMode, [['paste', 'Paste text'], ['file', 'Upload']])}</div>
          ${briefBlock}
          <input type="file" id="rv-brief-file" accept=".docx,.pdf" hidden>
          ${hasBrief ? `<div class="rv-reqs" aria-labelledby="rv-reqs-h">
              <h4 id="rv-reqs-h">Detected requirements</h4>
              <div id="rv-reqs-body" aria-live="polite">${rvReqsHtml()}</div>
            </div>` : '<p class="small muted" style="margin:0">With a brief we check your work against its requirements. Without it you get a basic check.</p>'}
        </div>
        <div class="card rv-block" id="rv-run">
          <label class="fld-label" for="rv-type">Document type</label>
          <select class="select fld-select" id="rv-type">
            ${R.docTypes.map(t => `<option ${rs.docType === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}
          </select>
          <div class="rv-run-row">
            <button class="btn btn-primary btn-lg" data-act="rv-run" id="rv-run-btn" ${rvHasDoc() && rs.status !== 'checking' ? '' : 'disabled'} ${rvHasDoc() ? '' : 'aria-describedby="rv-run-hint"'}>
              ${rs.status === 'checking' ? '<span class="spinner" aria-hidden="true"></span> Checking…' : 'Check document'}</button>
            <span class="badge">Free</span>
            <span class="small muted" id="rv-run-hint" ${rvHasDoc() ? 'hidden' : ''}>Add your document first</span>
          </div>
        </div>
      </section>
      <section class="rv-col" id="rv-results" aria-labelledby="rv-results-h">
        <h2 id="rv-results-h" tabindex="-1">Results</h2>
        <div class="card rv-results-card" aria-live="polite">${rvResultsBody()}</div>
      </section>
    </div>
  </div>`;
}

function rvResultsBody() {
  const rs = reviewState();
  if (rs.status === 'checking') {
    const n = rs.reqs && rs.reqs.status === 'done' ? rvReqLines(rs.reqs.parsed).length : 0;
    return `<div class="loading"><span class="spinner" aria-hidden="true"></span>
    ${workDocHasBrief() ? `Checking your work against ${n ? `${n} requirements` : 'the brief'}…` : 'Running a basic check…'}</div>`;
  }
  if (rs.status === 'done' && rs.result) return rvResultHtml(rs.result);
  // Empty: neutral hint + a dimmed example of what you will get
  const example = { full: true, score: 62, docType: 'Essay', items: [
    { label: 'Word count: 1,500', status: 'partly', reason: 'About 1,240 words (−17%).', action: 'editor', fix: 'Add about 260 words' },
    { label: 'Referencing: APA 7', status: 'met', reason: 'Citations follow APA 7.' },
    { label: 'Required section: Methodology', status: 'missing', reason: 'No section titled “Methodology” was found.', action: 'editor', fix: 'Add a Methodology section' },
    { label: 'Cover page', status: 'missing', reason: 'No cover page found.', action: 'format' },
  ] };
  return `<p class="rv-empty-hint">Add your document and brief to see your readiness score.</p>
    <div class="rv-example" aria-hidden="true" inert><span class="rv-example-label">Example</span>${rvResultHtml(example, { example: true })}</div>`;
}

function rerenderReview(focusSel) {
  const y = window.scrollY;
  $('#main').innerHTML = renderReview();
  bindReview();
  window.scrollTo(0, y);
  if (focusSel) {
    const el = $(focusSel);
    el?.focus({ preventScroll: true });
    if (el?.tagName === 'TEXTAREA') el.setSelectionRange(el.value.length, el.value.length);
  }
}

function bindReview() {
  const rs = reviewState();
  $$('input[name="rv-doc-mode"]').forEach(r => r.addEventListener('change', () => { rs.docMode = r.value; rerenderReview(`input[name="rv-doc-mode"][value="${r.value}"]`); }));
  $$('input[name="rv-brief-mode"]').forEach(r => r.addEventListener('change', () => { rs.briefMode = r.value; rerenderReview(`input[name="rv-brief-mode"][value="${r.value}"]`); }));
  const text = $('#rv-doc-text');
  if (text) text.addEventListener('input', () => {
    workDoc.text = text.value; workDoc.formatted = null;
    $('#rv-doc-words').textContent = `${fmtNum(countWords(workDoc.text))} words`;
    $('#rv-run-btn').disabled = !rvHasDoc() || rs.status === 'checking';
    $('#rv-run-hint').hidden = rvHasDoc();
  });
  const brief = $('#rv-brief-text');
  if (brief) brief.addEventListener('input', () => {
    const had = workDocHasBrief();
    workDoc.briefText = brief.value;
    clearTimeout(rs.reqTimer);
    if (workDocHasBrief()) {
      if (rs.reqs && rs.reqs.key !== rvBriefSource()?.key) { rs.reqs = null; rvRefreshReqs(); }
      rs.reqTimer = setTimeout(rvDetectReqs, 1200);
    }
    if (had !== workDocHasBrief()) rerenderReview('#rv-brief-text');   // show / hide detected requirements
  });
  $('#rv-type').addEventListener('change', (e) => { rs.docType = e.target.value; });
  const takeFile = (file, kind) => {
    if (!file) return;
    if (!/\.(docx|pdf)$/i.test(file.name)) { toast('Please choose a .docx or .pdf file'); return; }
    if (file.size > 16 * 1024 * 1024) { toast('The file is larger than 16 MB'); return; }
    if (kind === 'doc') { workDoc.file = { name: file.name, size: file.size, blob: file }; workDoc.formatted = null; }
    else workDoc.briefFile = { name: file.name, size: file.size, blob: file };
    rerenderReview(kind === 'doc' ? '[data-act="rv-remove-doc"]' : '[data-act="rv-remove-brief"]');
    if (kind === 'brief') rvDetectReqs();
  };
  [['#rv-doc-file', '#rv-doc-drop', 'doc'], ['#rv-brief-file', '#rv-brief-drop', 'brief']].forEach(([inSel, dropSel, kind]) => {
    $(inSel).addEventListener('change', (e) => takeFile(e.target.files[0], kind));
    const d = $(dropSel);
    if (!d) return;
    d.addEventListener('dragover', (e) => { e.preventDefault(); d.classList.add('drag'); });
    d.addEventListener('dragleave', () => d.classList.remove('drag'));
    d.addEventListener('drop', (e) => { e.preventDefault(); d.classList.remove('drag'); takeFile(e.dataTransfer.files[0], kind); });
  });
  // A brief added on another page (or a changed source) still needs reading
  const src = rvBriefSource();
  if (src && (!rs.reqs || rs.reqs.key !== src.key) && !rs.reqTimer) rvDetectReqs();
  if (rs.autoRun) { rs.autoRun = false; rvRun(); }
}

async function rvRun() {
  const rs = reviewState();
  if (!rvHasDoc() || rs.status === 'checking') return;
  const before = rs.result && workDoc.formatted ? rs.result.score : null;
  rs.status = 'checking';
  rerenderReview();
  if (mobileMQ.matches || window.innerWidth < 1000) $('#rv-results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  try {
    const reqs = workDocHasBrief() ? await rvDetectReqs() : null;
    const read = reqs && reqs.status === 'done';
    const data = await API.review.check({
      file: rs.docMode === 'file' ? workDoc.file.blob : null,
      text: rs.docMode === 'paste' ? workDoc.text : '',
      docType: rs.docType,
      requirements: read ? reqs.text : workDoc.briefText.trim(),
      parsed: read ? reqs.parsed : null,
    });
    rs.result = { ...rvMapResult(data, !!(data.meta && data.meta.has_assignment_brief)), before };
    rs.status = 'done';
    const today = new Date().toISOString().slice(0, 10);
    state.docs.unshift({ id: 'd' + Date.now(), title: `${rvDocName()} — review`, tool: 'check', date: today });
    saveDocs();
  } catch (err) {
    rs.status = 'idle';
    toast(err.message || 'The check failed. Try again.');
  }
  if (reviewState() === rs && currentRoute() === 'check') rerenderReview('#rv-results-h');
}

/* Work Review → Formatting: same document, style and settings filled from the detected requirements */
function rvFormatPrefill(p) {
  const values = {};
  if (!p) return { values };
  const styleId = { apa: 'apa', mla: 'mla', harvard: 'harvard', chicago: 'chicago', ieee: 'ieee' }[String(p.citation_style || '').toLowerCase().split(/\s/)[0]];
  const opts = CONFIG.format.options;
  if (p.font_family && opts.font.includes(p.font_family)) values.font = p.font_family;
  if (p.font_size && opts.size.includes(Number(p.font_size))) values.size = Number(p.font_size);
  const spacing = Number(p.spacing || p.line_spacing);
  if (spacing) values.lineSpacing = opts.lineSpacing.reduce((a, b) => (Math.abs(parseFloat(b) - spacing) < Math.abs(parseFloat(a) - spacing) ? b : a));
  if (p.cover_page_required != null) values.coverPage = !!p.cover_page_required;
  if ((p.required_sections || []).length) values.requiredSections = p.required_sections.join('\n');
  return { styleId, values };
}

function rvToFormatting() {
  const fs = fmtState(), rs = reviewState();
  const P = rvFormatPrefill(rs.reqs && rs.reqs.status === 'done' ? rs.reqs.parsed : null);
  fmtApplyStyle(P.styleId || fs.styleId, { fromBrief: !!P.styleId });
  Object.assign(fs.values, P.values);
  Object.assign(fs, {
    fromBrief: [...(P.styleId ? ['styleId'] : []), ...Object.keys(P.values)], fillSource: 'review', prefillBanner: true,
    styleTab: 'pick', briefStatus: 'idle', settingsOpen: true, status: 'idle',
    mode: rs.docMode === 'file' && fmtIsDocx(workDoc.file) ? 'file' : (workDoc.text.trim() ? 'paste' : fs.mode),
  });
  fs.groupsOpen.structure = true;
  go('format');
}

function rvToEditor(sectionList) {
  const sections = (sectionList || '').split('|').filter(Boolean);
  const paras = workDoc.text.trim() ? workDoc.text.split(/\n\s*\n|\n/).map(p => p.trim()).filter(Boolean) : CONFIG.format.sampleParagraphs;
  const title = rvDocName().replace(/\.(docx|pdf)$/i, '');
  edReplaceDoc(title, `<h1>${esc(title)}</h1>` + paras.map(p => `<p>${esc(p)}</p>`).join('')
    + sections.map(s => `<h2>${esc(s)}</h2><p>[Write your ${esc(s.toLowerCase())} here.]</p>`).join(''), 'Before opening from Work Review');
  go('workspace');
  if (sections.length) toast(`${sections.length === 1 ? `A “${sections[0]}” heading was` : `${sections.length} headings were`} added at the end. Fill them in.`);
}

function rvToAI() {
  if (!state.signedIn) return openSignup({ intent: 'turnitin' });
  const body = workDoc.text.trim();
  const blob = (reviewState().docMode === 'file' && workDoc.file?.blob) || new File([body], 'Your text.txt', { type: 'text/plain' });
  Object.assign(toolState('turnitin'), {
    file: { name: blob.name, size: blob.size, blob, text: body || null },
    note: `Your document from ${ITEMS.check.label} is attached. Press Check document.`,
  });
  go('turnitin');
}

function rvAction(act, el) {
  switch (act) {
    case 'rv-upload-doc': $('#rv-doc-file').click(); break;
    case 'rv-upload-brief': $('#rv-brief-file').click(); break;
    case 'rv-remove-doc': workDoc.file = null; workDoc.formatted = null; rerenderReview('#rv-doc-drop'); break;
    case 'rv-remove-brief': workDoc.briefFile = null; reviewState().reqs = null; rerenderReview('#rv-brief-drop'); break;
    case 'rv-run': rvRun(); break;
    case 'rv-use-reqs': case 'rv-fix-format': rvToFormatting(); break;
    case 'rv-editor': rvToEditor(el.dataset.section); break;
    case 'rv-ai': rvToAI(); break;
    case 'rv-add-brief': {
      reviewState().briefMode = 'paste';
      rerenderReview('#rv-brief-text');
      $('#rv-brief').scrollIntoView({ behavior: 'smooth', block: 'center' });
      break;
    }
  }
}

/* Veil access: guest → (low | locked) → active → expired */
const DAY = 86400000;
function veilAccess() {
  if (!state.signedIn) return 'guest';
  const v = state.veil || {};
  if (v.active && v.expiresAt && new Date(v.expiresAt) < new Date()) v.active = false;
  if (v.active) return 'active';
  if (v.expiresAt) return 'expired';
  return state.balance >= CONFIG.veil.price ? 'locked' : 'low';
}
const veilDaysLeft = () => Math.max(0, Math.ceil((new Date(state.veil.expiresAt) - new Date()) / DAY));
const fmtLong = (d) => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
const kbd = (k) => `<span class="kbd-group"><kbd class="kbd">Alt</kbd><kbd class="kbd">${esc(k)}</kbd></span>`;

// Static picture of Veil answering a quiz question (decorative, described for screen readers)
function veilDemoHtml() {
  return `<figure class="veil-demo">
    <figcaption class="visually-hidden">Example: a quiz question is selected on a course page and Veil answers it in a small panel on the same page.</figcaption>
    <div class="vd-window" aria-hidden="true">
      <div class="vd-bar"><span class="vd-dots"><i></i><i></i><i></i></span><span class="vd-url">canvas.university.edu/courses/bio-201/quizzes/3</span><span class="vd-ext">${icon('panel')}</span></div>
      <div class="vd-page">
        <p class="vd-meta">BIO 201 · Quiz 3 · Question 4 of 10</p>
        <p class="vd-q">Which process moves <mark>sodium ions out of the cell against their concentration gradient?</mark></p>
        <ul class="vd-opts"><li>Simple diffusion</li><li>Facilitated diffusion</li><li>Active transport</li><li>Osmosis</li></ul>
        <div class="vd-panel">
          <div class="vd-panel-head"><b>Veil</b><span>Detailed</span><span class="vd-toggle"></span></div>
          <div class="vd-panel-body">
            <p class="vd-quote">“…sodium ions out of the cell against their concentration gradient?”</p>
            <p><b>C — Active transport.</b> The sodium–potassium pump spends ATP to push 3 Na⁺ out and 2 K⁺ in, against the gradient. Diffusion and osmosis only move things from high to low concentration.</p>
            <p class="vd-follow"><span>Ask a follow-up…</span><span class="vd-send">${icon('send')}</span></p>
          </div>
        </div>
        <div class="vd-toast">${kbd('Q')}<span>Selection sent to Veil</span></div>
      </div>
    </div>
  </figure>`;
}

function veilShortcutDemo(kind) {
  if (kind === 'ask') return `<div class="vs-demo" aria-hidden="true"><p class="vs-text">Mitochondria make most of the cell’s ATP through <mark>oxidative phosphorylation</mark>.</p>
      <p class="vs-bubble">The last step of respiration: electrons move along a chain of proteins, and that energy drives ATP synthase.</p></div>`;
  if (kind === 'crop') return `<div class="vs-demo vs-crop" aria-hidden="true"><span class="vs-formula">∫<sub>0</sub><sup>1</sup> x² dx<i></i><i></i><i></i><i></i></span><span class="vs-bubble">= <b>1/3</b></span></div>`;
  return `<div class="vs-demo" aria-hidden="true"><span class="vs-label">Before</span><p class="vs-text">Furthermore, it is important to note that social media significantly impacts adolescent wellbeing.</p>
      <span class="vs-label vs-after">After</span><p class="vs-text vs-new">Social media shapes how teens feel about themselves — more than most of us admit.</p></div>`;
}

function renderVeil() {
  const V = CONFIG.veil, acc = veilAccess(), price = fmtCr(V.price);
  // Main button is always "Download for Chrome"; what it does depends on access:
  // guest → sign up, signed in without access → unlock first (too few credits: says how many and opens Pricing), active → download
  const ctaAct = { guest: 'signup', locked: 'veil-unlock', low: 'veil-unlock', active: 'veil-download', expired: 'veil-unlock' }[acc];
  const cta = `<button class="btn btn-primary btn-lg" data-act="${ctaAct}">${icon('chrome')} Download for Chrome</button>`;
  const note = {
    guest: `Free account first. Veil itself is ${price} credits for ${V.days} days.`,
    locked: `${V.days} days, every question included. You have ${fmtCr(state.balance)} credits.`,
    low: `You have ${fmtCr(state.balance)} credits — ${fmtCr(V.price - state.balance)} short of ${price}.`,
    active: `Active until ${fmtLong(state.veil.expiresAt)}. Already installed? You’re all set.`,
    expired: `Access ended ${fmtLong(state.veil.expiresAt).replace(/, \d{4}$/, '')}. Veil is still installed — renew to switch it back on.`,
  }[acc];
  const done = acc === 'active';
  const step = (n, title, body, extra = '') => `<li class="vstep ${n === 1 && done ? 'done' : ''}">
      <span class="vstep-num" aria-hidden="true">${n === 1 && done ? icon('check') : n}</span>
      <div><h3>${title}${n === 1 && done ? '<span class="visually-hidden"> (done)</span>' : ''}</h3><p class="muted">${body}</p>${extra}</div>
    </li>`;
  const activeChip = acc === 'active' ? `<span class="lvl lvl-low veil-active-chip">Active · ${veilDaysLeft()} days left</span>` : '';
  return `<div class="page veil-page">
    ${pageHead(ITEMS.veil, '', activeChip)}

    <section class="veil-hero" aria-labelledby="veil-hero-h">
      <div class="veil-hero-text">
        <h2 id="veil-hero-h">${esc(V.headline)}</h2>
        <p class="veil-lead">Veil is a small panel that opens over any tab. Select a question, press <b>Alt+Q / control+Q</b> — the answer shows up right next to it. Select your own text, press <b>Alt+H / option+H</b> — it comes back humanized.</p>
        <div class="veil-cta">${cta}<button class="btn btn-lg btn-ghost" data-act="${acc === 'guest' ? 'signup' : 'topup'}">${icon('plus')} Top up credits</button></div>
        <p class="veil-note ${acc === 'low' || acc === 'expired' ? 'is-warn' : ''}">${note}</p>
      </div>
      ${veilDemoHtml()}
    </section>

    <section class="veil-sec" aria-labelledby="veil-how-h">
      <div class="veil-sec-head"><h2 id="veil-how-h">Three shortcuts. That’s the whole manual.</h2>
        <p class="muted">Keep reading. Veil works on top of the page, so you never lose your place.</p></div>
      <div class="veil-features">${V.shortcuts.map(f => `<article class="card veil-feature">
          ${veilShortcutDemo(f.demo)}
          ${kbd(f.key)}
          <h3>${esc(f.title)}</h3>
          <p class="muted">${esc(f.text)}</p>
        </article>`).join('')}</div>
    </section>

    <section class="veil-sec" id="veil-get" aria-labelledby="veil-get-h" tabindex="-1">
      <div class="veil-sec-head"><h2 id="veil-get-h">Get Veil in about 3 minutes</h2>
        <p class="muted">Unlock it here, then add it to Chrome. You install once — renewing later just switches it back on.</p></div>
      <div class="veil-get">
        <section class="card veil-phone" aria-labelledby="veil-phone-h">
          <span class="vc-logo vc-logo-soft" aria-hidden="true">${icon('laptop')}</span>
          <h3 id="veil-phone-h">Veil runs in Chrome on a computer</h3>
          <p class="muted">You can unlock it here, but install it from your laptop. We’ll send you the link so you don’t have to look for it.</p>
          <button class="btn btn-primary btn-lg" data-act="veil-email">${icon('mail')} Email me the link</button>
        </section>
        <ol class="veil-steps">
          ${step(1, 'Unlock Veil', `Pay ${price} credits from your balance. Access lasts ${V.days} days.`)}
          ${step(2, 'Download and unzip', 'You’ll get a folder called <b>Veil</b>. Keep it somewhere safe — Chrome runs Veil from that folder, so don’t delete it.',
            done ? `<button class="btn btn-sm btn-primary" data-act="veil-download">${icon('download')} Download Veil.zip</button>` : '')}
          ${step(3, 'Add it to Chrome', 'Open the extensions page, turn on <b>Developer mode</b> (top right), click <b>Load unpacked</b> and choose the Veil folder.',
            `<span class="vstep-code"><code>${esc(V.extensionsUrl)}</code><button class="btn btn-sm" data-act="veil-copy" aria-label="Copy address ${esc(V.extensionsUrl)}">${icon('copy')} Copy</button></span>`)}
          ${step(4, 'Pin it and sign in', 'Click the puzzle icon in Chrome, pin Veil, open it and sign in with your DocMaxxing account.')}
          <li class="vstep-done">${icon('sparkles')}<span>Done. Select any text and press <b>Alt+Q</b>. On a Mac, use <b>Option</b> instead of Alt.</span></li>
        </ol>
      </div>
    </section>

    <section class="veil-faq" aria-labelledby="veil-faq-h">
      <h2 id="veil-faq-h">Questions</h2>
      <div class="veil-faq-list">${V.faq.map(([q, a]) => `<details><summary>${esc(veilFill(q))}${icon('plus')}</summary><p class="muted">${esc(veilFill(a))}</p></details>`).join('')}</div>
    </section>
  </div>`;
}

// FAQ copy mentions the price and the length of the pass
const veilFill = (text) => text.replace(/\{price\}/g, fmtCr(CONFIG.veil.price)).replace(/\{days\}/g, CONFIG.veil.days);

// Unlock / renew / extend: confirm, then success with the download
const veilDlg = $('#veil-dialog');
function openVeilConfirm() {
  const V = CONFIG.veil, acc = veilAccess();
  if (state.balance < V.price) {
    toast(`You need ${fmtCr(V.price - state.balance)} more credits`);
    state.returnTo = 'veil'; go('pricing'); return;
  }
  const from = acc === 'active' ? new Date(state.veil.expiresAt) : new Date();
  const until = new Date(from.getTime() + V.days * DAY);
  veilDlg.innerHTML = `<h2 id="veil-dlg-title">${acc === 'active' ? `Add ${V.days} days to Veil?` : `Unlock Veil for ${V.days} days?`}</h2>
    <p class="muted">We’ll take ${fmtCr(V.price)} credits from your balance. Access ends on its own — nothing renews automatically.</p>
    <dl class="vc-box veil-sum">
      <div><dt>Balance now</dt><dd>${fmtCr(state.balance)}</dd></div>
      <div><dt>Veil, ${V.days} days</dt><dd>−${fmtCr(V.price)}</dd></div>
      <div class="veil-sum-total"><dt>Balance after</dt><dd>${fmtCr(state.balance - V.price)}</dd></div>
      <div><dt>Active until</dt><dd>${fmtLong(until)}</dd></div>
    </dl>
    <div class="dialog-actions">
      <button class="btn" type="button" data-act="veil-dlg-close">Cancel</button>
      <button class="btn btn-primary" type="button" data-act="veil-confirm">Unlock · ${fmtCr(V.price)}</button>
    </div>`;
  veilDlg.showModal();
  $('[data-act="veil-confirm"]', veilDlg).focus();
}
async function veilConfirm(btn) {
  btn.disabled = true; btn.textContent = 'Unlocking…';
  let data;
  try {
    data = await API.veil.unlock();
  } catch (err) {
    btn.disabled = false; btn.textContent = `Unlock · ${fmtCr(CONFIG.veil.price)}`;
    const info = apiErrorInfo(err, { intent: 'veil' });
    if (info.handled || info.action === 'topup') veilDlg.close();
    if (info.action === 'topup') {
      if (err.data && typeof err.data.balance === 'number') state.balance = err.data.balance;
      state.returnTo = 'veil'; go('pricing');
    }
    if (!info.handled) toast(info.message || 'Could not unlock Veil. Try again.');
    return;
  }
  state.balance = data.balance;
  state.veil = { ...data.veil };
  loadCredits();
  veilDlg.innerHTML = `<span class="veil-ok" aria-hidden="true">${icon('check')}</span>
    <h2 id="veil-dlg-title">Veil is unlocked</h2>
    <p class="muted">Active until ${fmtLong(state.veil.expiresAt)}. Now add it to Chrome — it takes about 3 minutes.</p>
    <button class="btn btn-primary btn-lg btn-block" type="button" data-act="veil-download">${icon('download')} Download Veil.zip</button>
    <div class="veil-ok-foot"><a href="#veil-get" data-act="veil-steps">Show install steps</a><span class="muted">Already installed? <button class="link-btn" type="button" data-act="veil-dlg-close">Close this</button></span></div>`;
  renderSidebar(); render();
  if (!veilDlg.open) veilDlg.showModal();
  $('[data-act="veil-download"]', veilDlg).focus();
}
veilDlg.addEventListener('click', (e) => { if (e.target === veilDlg) veilDlg.close(); });

async function veilEmailLink(btn) {
  if (!state.signedIn) { toast('Sign up first, then we can email you the link'); return; }
  btn.disabled = true;
  try {
    const data = await API.veil.emailLink();
    toast(`We’ve emailed the link to ${data.email}`);
  } catch (err) {
    toast(err.message || 'Could not send the email. Try again.');
  }
  btn.disabled = false;
}

function veilAction(act, el) {
  const V = CONFIG.veil;
  switch (act) {
    case 'veil-unlock': openVeilConfirm(); break;
    case 'veil-confirm': veilConfirm(el); break;
    case 'veil-dlg-close': veilDlg.close(); break;
    case 'veil-download':
      if (veilAccess() === 'active') location.href = V.zipUrl;
      else openVeilConfirm();
      break;
    case 'veil-steps': veilDlg.close(); $('#veil-get')?.scrollIntoView({ behavior: 'smooth' }); $('#veil-get')?.focus({ preventScroll: true }); break;
    case 'veil-scroll': $('#veil-get')?.scrollIntoView({ behavior: 'smooth' }); $('#veil-get')?.focus({ preventScroll: true }); break;
    case 'veil-copy': navigator.clipboard?.writeText(V.extensionsUrl).catch(() => {}); toast('Copied. Paste it into Chrome’s address bar'); break;
    case 'veil-email': veilEmailLink(el); break;
  }
}


/* ---------- Pricing: 3 plans + one-time credits ---------- */
const fmtCr = (n) => n.toLocaleString('en-US');

// One line: ✓/✕ · name · amount on the right
function planRowHtml(r) {
  const ok = r.ok !== false;
  return `<li class="pl-row ${ok ? '' : 'off'}" ${r.hint ? `data-tip-title="${esc(r.label)}" data-tip-desc="${esc(r.hint)}" tabindex="0"` : ''}>
    <span class="pl-mark" aria-hidden="true">${icon(ok ? 'check' : 'xmark')}</span>
    <span class="pl-label">${esc(r.label)}${ok ? '' : '<span class="visually-hidden"> (not included)</span>'}${r.hint ? `<span class="visually-hidden">: ${esc(r.hint)}</span>` : ''}</span>
    ${r.value ? `<span class="pl-val">${esc(r.value)}</span>` : ''}
  </li>`;
}

function planHtml(p, { compact = false } = {}) {
  const badges = (p.badges || []).map(b => `<span class="pl-badge pl-badge-${b.kind}">${esc(b.text)}</span>`).join('');
  return `<article class="plan ${p.highlight ? 'plan-hl' : ''}" aria-labelledby="plan-${p.id}">
    <div class="plan-top">
      <div class="plan-name-row"><h2 id="plan-${p.id}">${esc(p.name)}${p.sub ? ` <span class="plan-sub">${esc(p.sub)}</span>` : ''}</h2>${badges}</div>
      <p class="plan-price"><b>$${p.price}</b><span>/ month</span></p>
      <p class="plan-tagline">${esc(p.tagline)}</p>
      <button class="btn btn-block ${p.highlight ? 'btn-primary' : 'btn-dark'}" data-act="plan-pick" data-plan="${p.id}">${esc(planCta(p))}</button>
    </div>
    <div class="plan-body">
      <div class="plan-credits">
        <p><b>${fmtCr(p.credits)} credits</b> <span>/ mo</span></p>
        <ul>${p.perks.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      </div>
      <section class="pl-sec pl-sec-free ${p.freeStyle === 'plain' ? '' : 'pl-sec-green'}" aria-labelledby="plan-${p.id}-free">
        <h3 id="plan-${p.id}-free">Free generations</h3>
        <ul>${p.free.map(planRowHtml).join('')}</ul>
      </section>
      ${compact ? '' : `<section class="pl-sec pl-sec-unl ${p.unlimitedStyle === 'outline' ? 'pl-sec-outline' : ''}" aria-labelledby="plan-${p.id}-unl">
        <h3 id="plan-${p.id}-unl">Unlimited & stealth</h3>
        <ul>${p.unlimited.map(planRowHtml).join('')}</ul>
      </section>`}
    </div>
  </article>`;
}

function paygValues(cr) {
  const P = CONFIG.pricing.payg;
  const steps = cr / P.step;
  return {
    price: P.baseUsd + steps * P.usdPerStep,
    scans: Math.floor(cr / P.creditsPerScan),
    runs: Math.floor(cr / P.creditsPerRun),
    creditPackQuantity: steps,
  };
}

function renderPricing() {
  const P = CONFIG.pricing, G = P.payg, cr = state.paygCredits || G.start, v = paygValues(cr);
  return `<div class="page pricing">
    <header class="pricing-head">
      <h1>${esc(P.title)}</h1>
      <p class="lead">${esc(P.subtitle)}</p>
    </header>
    <div class="plans">${P.plans.map(p => planHtml(p)).join('')}</div>
    <section class="payg" id="payg" aria-labelledby="payg-h">
      <div class="payg-head">
        <div><h2 id="payg-h">${esc(G.title)}</h2><p class="muted">${esc(G.lead)}</p></div>
        <span class="pl-badge pl-badge-green"><span class="pl-mark" aria-hidden="true">${icon('check')}</span>${esc(G.badge)}</span>
      </div>
      <div class="payg-main">
        <div class="payg-slider">
          <div class="payg-amount"><label for="payg-range">Credits</label><output id="payg-credits" for="payg-range">${fmtCr(cr)}</output></div>
          <input type="range" class="range range-lg" id="payg-range" min="${G.min}" max="${G.max}" step="${G.step}" value="${cr}"
            aria-valuetext="${fmtCr(cr)} credits for $${v.price}" style="--fill:${(cr - G.min) / (G.max - G.min) * 100}%">
          <div class="range-scale" aria-hidden="true"><span>${fmtCr(G.min)}</span><span>${fmtCr(G.max)}</span></div>
        </div>
        <div class="payg-sum">
          <p class="payg-price"><b id="payg-price">$${v.price}</b><span>one-time</span></p>
          <p class="payg-worth" id="payg-worth">= <b>${v.scans}</b> Turnitin checks or <b>${v.runs}</b> Humanize runs</p>
          <button class="btn btn-primary btn-block" data-act="payg-buy">${esc(G.cta)}</button>
        </div>
      </div>
    </section>
  </div>`;
}

function planCta(p) {
  if (!state.signedIn || CONFIG.billing.plan !== p.id) return p.cta;
  const sub = state.billing?.subscription;
  return sub && sub.status !== 'expired' ? 'Manage subscription' : 'Extend for a month';
}

// Back from checkout (?paid=1): the webhook usually lands within seconds, so poll until it shows.
function watchPaymentReturn() {
  const params = new URLSearchParams(location.search);
  if (params.get('paid') !== '1') return;
  params.delete('paid');
  history.replaceState(null, '', location.pathname + (params.size ? '?' + params : '') + location.hash);
  if (!state.signedIn) return;
  toast('Payment received. Your plan and credits will appear in a few seconds.');
  const since = Date.now() - 15 * 60000;
  const utc = d => (/[zZ]$|[+-]\d\d:?\d\d$/.test(d) ? d : d.replace(' ', 'T') + 'Z');
  const isRecent = p => p.status === 'Paid' && Date.parse(utc(String(p.date))) >= since;
  let tries = 0;
  const tick = async () => {
    tries += 1;
    await Promise.all([loadCredits(), loadBilling(true)]);
    if ((state.billing?.payments || []).some(isRecent)) {
      const back = ALL_ITEMS.find(i => i.route === sessionStorage.getItem('dmx-return-to'));
      sessionStorage.removeItem('dmx-return-to');
      toast('Payment confirmed. Thank you!' + (back ? ` · back to ${back.label}` : ''));
      if (back && back.route !== currentRoute()) go(back.route);
      return;
    }
    if (tries < 12) setTimeout(tick, 5000);
    else toast('Still waiting for the payment confirmation. Refresh in a minute or contact support.');
  };
  setTimeout(tick, 3000);
}

async function startCheckout(what, btn) {
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = 'Opening checkout…';
  try {
    const res = await API.checkout(what);
    if (!res.payment_url) throw new Error('Checkout is not available right now.');
    if (res.manage && what.plan && what.plan !== CONFIG.billing.plan) {
      toast('You already have a subscription. To switch plans, cancel it in the portal, then pick the new plan.');
      await new Promise(r => setTimeout(r, 2500));
    }
    if (state.returnTo) sessionStorage.setItem('dmx-return-to', state.returnTo);
    location.href = res.payment_url;
  } catch (err) {
    btn.disabled = false; btn.textContent = label;
    if (err.code === 'AUTH_REQUIRED') return onSignedOut();
    toast(err.code === 'CRYPTOMUS_NOT_CONFIGURED' ? 'Payments are not available right now.' : (err.message || 'Checkout failed. Please try again.'));
  }
}

function bindPricing() {
  const P = CONFIG.pricing, G = P.payg;
  const pr = $('#payg-range');
  pr.addEventListener('input', () => {
    const cr = state.paygCredits = +pr.value, v = paygValues(cr);
    $('#payg-credits').textContent = fmtCr(cr);
    $('#payg-price').textContent = '$' + v.price;
    $('#payg-worth').innerHTML = `= <b>${v.scans}</b> Turnitin checks or <b>${v.runs}</b> Humanize runs`;
    pr.style.setProperty('--fill', (cr - G.min) / (G.max - G.min) * 100 + '%');
    pr.setAttribute('aria-valuetext', `${fmtCr(cr)} credits for $${v.price}`);
  });
}

/* ---------- Earn & Share (referral program) ---------- */
const money = (n) => '$' + n.toFixed(2);
const earnLink = () => earnState().link || CONFIG.earn.linkBase + CONFIG.earn.code;
const refTotal = (r) => r.deposits.reduce((sum, d) => sum + d[1], 0);
const refQualified = (r) => r.qualified ?? r.deposits.some(d => d[1] >= CONFIG.earn.qualifyDeposit);
function earnState() {
  if (!state.earn) state.earn = { balance: 0, open: {}, loaded: false, loading: false, link: '', refs: [], qualified: 0 };
  return state.earn;
}

function applyReferralProfile(p) {
  const E = CONFIG.earn, es = earnState();
  Object.assign(E, {
    code: p.referral_code,
    creditsPerDollar: Number(p.usd_to_coins) || E.creditsPerDollar,
    convertBonus: Number(p.convert_multiplier) || E.convertBonus,
    minWithdraw: Number(p.min_withdraw_usd) || E.minWithdraw,
    freeTurnitin: Number(p.free_turnitin_reports) || 0,
  });
  Object.assign(es, {
    loaded: true,
    link: p.referral_link || '',
    balance: Number(p.referral_balance_usd) || 0,
    qualified: Number(p.qualifying_referrals_count) || 0,
    refs: (p.referrals || []).map(r => ({
      id: 'U-' + r.id,
      joined: String(r.joined_at || '').slice(0, 10),
      qualified: !!r.qualified,
      deposits: (r.history || []).map(h => [String(h.created_at || '').slice(0, 10), Number(h.amount_usd) || 0]),
    })),
  });
}

async function loadEarn(force = false) {
  const es = earnState();
  if (!state.signedIn || es.loading || (es.loaded && !force)) return;
  es.loading = true;
  try {
    applyReferralProfile(await API.referral.me());
  } catch (err) {
    if (err.code === 'AUTH_REQUIRED') return onSignedOut();
    toast(err.message || 'Could not load your referral data');
  } finally {
    es.loading = false;
  }
  if (currentRoute() === 'earn') render();
}

function renderEarn() {
  const E = CONFIG.earn, es = earnState(), refs = state.signedIn ? es.refs : [];
  if (state.signedIn && !es.loaded) loadEarn();
  const qualified = state.signedIn ? es.qualified : 0, maxF = E.milestones[E.milestones.length - 1].friends;
  const canWithdraw = es.balance >= E.minWithdraw, convertCr = Math.round(es.balance * E.creditsPerDollar * E.convertBonus);
  const shareUrl = (t) => t.url.replace('{link}', encodeURIComponent(earnLink())).replace('{text}', encodeURIComponent(E.shareText));
  const linkCard = state.signedIn ? `
      <div class="earn-link">
        <label class="visually-hidden" for="earn-link">Referral link</label>
        <input class="field-input" id="earn-link" readonly value="${esc(earnLink())}">
        <button class="btn btn-primary" data-act="earn-copy" data-copy="link">${icon('copy')} Copy</button>
      </div>
      <div class="earn-chips">
        <button class="earn-chip" data-act="earn-copy" data-copy="code" aria-label="Copy code ${esc(E.code)}" data-tip-title="Copy code" data-tip-desc="" data-tip-pos="bottom">Code <b class="mono">${esc(E.code)}</b>${icon('copy')}</button>
        <span class="earn-chip">Referred <b>${refs.length}</b></span>
        <span class="earn-chip">Free Turnitin reports <b>${E.freeTurnitin}</b></span>
      </div>
      <div class="earn-share"><span class="small muted">Share</span>
        ${E.share.map(t => `<a class="if-social app-tile app-${t.icon}" href="${esc(shareUrl(t))}" ${t.url.startsWith('mailto') ? '' : 'target="_blank" rel="noopener"'} aria-label="Share on ${esc(t.label)}" data-tip-title="${esc(t.label)}" data-tip-desc="" data-tip-pos="bottom">${appIcon(t.icon)}</a>`).join('')}
      </div>`
    : `<div class="earn-guest"><p class="muted">Create a free account to get your personal link and code.</p>
        <button class="btn btn-primary" data-act="signup">Sign up</button></div>`;

  const rows = refs.map(r => {
    const open = !!es.open[r.id], total = refTotal(r), ok = refQualified(r);
    return `<li class="ref ${open ? 'open' : ''}">
      <button class="ref-row" data-act="earn-ref" data-id="${r.id}" aria-expanded="${open}" aria-controls="ref-${r.id}">
        <span class="ref-id mono">${esc(r.id)}</span>
        <span class="ref-cell muted">Joined ${fmtDate(r.joined)}</span>
        <span class="ref-cell">${money(total)} <span class="muted">deposited</span></span>
        <span class="ref-cell"><b>${money(total * E.cashbackPct / 100)}</b> <span class="muted">cashback</span></span>
        <span class="lvl ${ok ? 'lvl-low' : 'lvl-medium'}">${ok ? 'Qualified' : 'Not yet'}</span>
        ${icon('chevronDown')}
      </button>
      <div class="ref-detail" id="ref-${r.id}" ${open ? '' : 'hidden'}>
        ${r.deposits.length ? `<ul>${r.deposits.map(d => `<li><span class="muted">${fmtDate(d[0])}</span><span>Deposit ${money(d[1])}</span><span class="free">+${money(d[1] * E.cashbackPct / 100)}</span></li>`).join('')}</ul>`
          : `<p class="muted small">No deposits yet. A friend counts after a deposit of $${E.qualifyDeposit} or more.</p>`}
      </div>
    </li>`;
  }).join('');

  return `<div class="page earn-page">
    ${pageHead(ITEMS.earn)}
    <div class="earn-top">
      <section class="card earn-card" aria-labelledby="earn-link-h">
        <h2 id="earn-link-h">Your link</h2>
        <p class="muted">Give ${E.giveCredits} credits, get ${E.cashbackPct}% cashback on their deposits.</p>
        ${linkCard}
      </section>
      <section class="card earn-card earn-wallet" aria-labelledby="earn-wallet-h">
        <h2 id="earn-wallet-h">${icon('wallet')} Wallet balance</h2>
        <p class="earn-balance" id="earn-balance">${money(state.signedIn ? es.balance : 0)}</p>
        <p class="muted">Convert to credits at a ${E.convertBonus}× bonus rate.</p>
        <div class="earn-actions">
          <button class="btn btn-primary" data-act="earn-convert" ${state.signedIn && es.balance > 0 ? '' : 'disabled'}
            ${es.balance > 0 ? `data-tip-title="Convert to credits" data-tip-desc="${money(es.balance)} = ${fmtCr(convertCr)} credits" data-tip-pos="bottom"` : ''}>Convert to credits · ${E.convertBonus}×</button>
          <span class="earn-withdraw-wrap" ${canWithdraw ? '' : `tabindex="0" data-tip-title="Withdraw funds" data-tip-desc="Available when balance reaches $${E.minWithdraw}" data-tip-pos="bottom"`}>
            <button class="btn" data-act="earn-withdraw" ${state.signedIn && canWithdraw ? '' : 'disabled'} ${canWithdraw ? '' : 'aria-describedby="earn-min"'}>Withdraw funds</button>
          </span>
        </div>
        ${canWithdraw ? '' : `<p class="small muted" id="earn-min">Withdraw from $${E.minWithdraw}.</p>`}
      </section>
    </div>

    <section class="card earn-card" aria-labelledby="earn-ms-h">
      <div class="earn-ms-head">
        <h2 id="earn-ms-h">Milestones & rewards</h2>
        <span class="small muted">${qualified} of ${maxF} qualifying friends</span>
      </div>
      <p class="muted">A friend counts only after they deposit $${E.qualifyDeposit}+ once.</p>
      <div class="ms-track" role="progressbar" aria-labelledby="earn-ms-h" aria-valuemin="0" aria-valuemax="${maxF}" aria-valuenow="${qualified}" aria-valuetext="${qualified} of ${maxF} qualifying friends">
        <span class="ms-fill" style="width:${Math.min(100, qualified / maxF * 100)}%"></span>
      </div>
      <ol class="ms-list">${E.milestones.map(m => {
        const done = qualified >= m.friends;
        return `<li class="ms ${done ? 'done' : ''}" style="left:${m.friends / maxF * 100}%">
          <span class="ms-dot" aria-hidden="true">${done ? icon('check') : m.friends}</span>
          <span class="ms-text"><b>${m.friends} friend${m.friends > 1 ? 's' : ''}</b><span>${esc(m.reward)}</span></span>
          ${done ? '<span class="visually-hidden"> (unlocked)</span>' : ''}
        </li>`;
      }).join('')}</ol>
    </section>

    <section class="card earn-card" aria-labelledby="earn-refs-h">
      <h2 id="earn-refs-h">Your referrals</h2>
      <p class="muted">IDs only, no emails. Open a row to see deposit history.</p>
      ${state.signedIn && refs.length ? `<ul class="refs">${rows}</ul>`
        : `<div class="empty"><strong>No referrals yet</strong>Share your link to invite friends and start earning cashback.</div>`}
    </section>
  </div>`;
}

const withdrawDlg = $('#withdraw-dialog');
function openWithdraw() {
  const E = CONFIG.earn, es = earnState();
  withdrawDlg.innerHTML = `<form class="withdraw-form" id="withdraw-form" novalidate>
    <div class="tut-head"><h2 id="withdraw-title">Withdraw funds</h2>
      <button class="icon-btn" type="button" data-act="withdraw-close" aria-label="Close">${icon('close')}</button></div>
    <label class="field" for="wd-amount"><span>Amount (USD)</span>
      <input class="field-input" id="wd-amount" type="number" inputmode="decimal" min="${E.minWithdraw}" max="${es.balance}" step="0.01" value="${es.balance.toFixed(2)}" required></label>
    <label class="field" for="wd-details"><span>Wallet ID / payment details</span>
      <input class="field-input" id="wd-details" autocomplete="off" required></label>
    <p class="small muted">Funds are reserved immediately. Minimum withdrawal: $${E.minWithdraw}.</p>
    <div class="dialog-actions"><button class="btn" type="button" data-act="withdraw-close">Cancel</button>
      <button class="btn btn-primary" type="submit">Submit request</button></div>
  </form>`;
  withdrawDlg.showModal();
  $('#withdraw-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const amt = +$('#wd-amount').value, details = $('#wd-details').value.trim();
    if (!(amt >= E.minWithdraw && amt <= es.balance)) { $('#wd-amount').setAttribute('aria-invalid', 'true'); return $('#wd-amount').focus(); }
    if (!details) { $('#wd-details').setAttribute('aria-invalid', 'true'); return $('#wd-details').focus(); }
    const btn = $('#withdraw-form [type=submit]');
    btn.disabled = true;
    try {
      const res = await API.referral.withdraw(amt, details);
      es.balance = Number(res.referral_balance_usd ?? es.balance - amt);
      withdrawDlg.close(); render();
      toast(`Withdrawal request for ${money(amt)} sent`);
    } catch (err) {
      btn.disabled = false;
      toast(err.message || 'Could not send the request');
    }
  });
}
withdrawDlg.addEventListener('click', (e) => { if (e.target === withdrawDlg) withdrawDlg.close(); });

function earnAction(act, el) {
  const E = CONFIG.earn, es = earnState();
  if (act === 'earn-copy') {
    const v = el.dataset.copy === 'code' ? E.code : earnLink();
    navigator.clipboard?.writeText(v).catch(() => {});
    toast(el.dataset.copy === 'code' ? 'Code copied' : 'Link copied');
  } else if (act === 'earn-ref') {
    es.open[el.dataset.id] = !es.open[el.dataset.id];
    render(); $(`[data-act="earn-ref"][data-id="${el.dataset.id}"]`)?.focus();
  } else if (act === 'earn-convert') {
    if (!(es.balance > 0)) return;
    el.disabled = true;
    API.referral.convert(es.balance).then(res => {
      es.balance = Number(res.referral_balance_usd ?? 0);
      if (res.balance != null) state.balance = Number(res.balance);
      renderSidebar(); render(); loadCredits();
      toast(`${fmtCr(Number(res.credits) || 0)} credits added to your balance`);
    }).catch(err => { el.disabled = false; toast(err.message || 'Could not convert'); });
  } else if (act === 'earn-withdraw') openWithdraw();
  else if (act === 'withdraw-close') withdrawDlg.close();
}

/* ---------- Legal pages: document list on the left, text on the right ---------- */
function legalItemHtml(t) {
  const i = t.indexOf(' — ');
  return i > 0 && i < 40 ? `<b>${esc(t.slice(0, i))}</b> — ${esc(t.slice(i + 3))}` : esc(t);
}

// Side menu shared by the information pages and Account
function infoNavHtml(current) {
  const label = (id) => id === 'contact' ? 'Contact' : (ITEMS[id] || {}).label;
  const href = (id) => id === 'contact' ? '#/help' : '#/' + id;
  return `<nav class="legal-nav" aria-labelledby="legal-nav-h">
    <p class="legal-nav-h" id="legal-nav-h">Policies</p>
    <ul>${CONFIG.infoNav.map(id => `<li><a href="${href(id)}" ${id === current ? 'aria-current="page"' : ''}>${esc(label(id))}</a></li>`).join('')}</ul>
    <a class="legal-back" href="#/help">${icon('arrow')} Back to Help</a>
  </nav>`;
}

function renderLegal(id) {
  const d = CONFIG.legal.find(x => x.id === id), C = CONFIG.help;
  const contact = `<a href="mailto:${esc(C.email)}">${esc(C.email)}</a> · WhatsApp <a href="https://wa.me/${C.phone.replace(/\D/g, '')}" target="_blank" rel="noopener">${esc(C.phone)}</a>`;
  const body = d.sections.map(sec => `<section class="legal-sec">
      ${sec.h ? `<h2>${esc(sec.h)}</h2>` : ''}
      ${(sec.p || []).map(x => `<p>${esc(x)}</p>`).join('')}
      ${sec.list ? `<ul>${sec.list.map(x => `<li>${legalItemHtml(x)}</li>`).join('')}</ul>` : ''}
      ${sec.qa ? `<dl class="legal-qa">${sec.qa.map(([q, a]) => `<div><dt>${esc(q)}</dt><dd>${esc(a)}</dd></div>`).join('')}</dl>` : ''}
      ${(sec.after || []).map(x => `<p>${esc(x)}</p>`).join('')}
      ${sec.contact != null ? `<p>${esc(sec.contact)} ${contact}</p>` : ''}
      ${sec.related ? `<p class="legal-related">${sec.related.map(r => `<a href="#/${r}">${esc(ITEMS[r].label)}</a>`).join('')}</p>` : ''}
    </section>`).join('');
  return `<div class="page legal-page">
    <div class="legal-layout">
      ${infoNavHtml(id)}
      <article class="card legal-doc" aria-labelledby="legal-h">
        <header class="legal-head">
          <h1 id="legal-h">${esc(d.title)}</h1>
          <p class="lead">${esc(d.lead)}</p>
          ${d.updated ? `<p class="legal-updated">${esc(d.updated)}</p>` : ''}
        </header>
        ${body}
      </article>
    </div>
  </div>`;
}

/* ---------- Account: profile + password ---------- */
function renderAccount() {
  const u = CONFIG.user;
  if (!state.signedIn) return `<div class="page">${pageHead(ITEMS.settings)}
    <section class="card earn-card"><div class="earn-guest"><p class="muted">Sign in to manage your profile and password.</p>
      <button class="btn btn-primary" data-act="signup">Sign up</button></div></section></div>`;
  const pw = (id, label, ac, hint = '') => `<div class="field">
      <label for="${id}">${label}</label>
      <span class="pw-wrap">
        <input class="field-input" id="${id}" type="password" autocomplete="${ac}" ${hint ? `aria-describedby="${id}-hint"` : ''}>
        <button type="button" class="icon-btn pw-eye" data-act="acc-toggle-pw" data-for="${id}" aria-label="Show password" aria-pressed="false">${icon('eye')}</button>
      </span>
      ${hint ? `<span class="small muted" id="${id}-hint">${hint}</span>` : ''}
    </div>`;
  return `<div class="page account-page">
    ${pageHead(ITEMS.settings)}
    <div class="acc-grid">
      <section class="card acc-card" aria-labelledby="acc-profile-h">
        <h2 id="acc-profile-h">Profile</h2>
        <div class="acc-avatar">
          <span class="avatar avatar-lg" aria-hidden="true">${avatarInner()}</span>
          <div>
            <div class="acc-avatar-btns">
              <button type="button" class="btn btn-sm" data-act="acc-avatar" data-tip-title="Change avatar" data-tip-desc="PNG, JPG or WebP · up to 2 MB" data-tip-pos="bottom">${icon('upload')} Change avatar</button>
              ${state.avatarUrl ? '<button type="button" class="btn btn-sm btn-ghost" data-act="acc-avatar-remove">Remove</button>' : ''}
            </div>
            <input type="file" id="acc-avatar-file" accept="image/png,image/jpeg,image/webp" hidden>
          </div>
        </div>
        <form id="acc-profile-form" novalidate>
          <div class="field">
            <label for="acc-name">Displayed name</label>
            <input class="field-input" id="acc-name" autocomplete="nickname" maxlength="40" value="${esc(u.name)}" aria-describedby="acc-name-err">
            <span class="field-err" id="acc-name-err" hidden>Enter a name</span>
          </div>
          <dl class="acc-rows">
            <div><dt>ID</dt><dd class="mono">${esc(u.id)}</dd></div>
            <div><dt>Email</dt><dd>${esc(u.email)}</dd></div>
            <div><dt>Plan</dt><dd>${esc(planLabel())} <a class="acc-link" href="#/billing">Manage</a></dd></div>
          </dl>
          <div class="acc-actions"><button type="submit" class="btn btn-primary">Save changes</button></div>
        </form>
      </section>

      <section class="card acc-card" aria-labelledby="acc-pw-h">
        <h2 id="acc-pw-h">Change password</h2>
        <form id="acc-pw-form" novalidate>
          ${pw('acc-pw-cur', 'Current password', 'current-password')}
          ${pw('acc-pw-new', 'New password', 'new-password', `At least ${u.minPassword} characters`)}
          ${pw('acc-pw-confirm', 'Confirm new password', 'new-password')}
          <p class="field-err" id="acc-pw-err" role="alert" hidden></p>
          <div class="acc-actions"><button type="submit" class="btn">Update password</button></div>
        </form>
      </section>
    </div>
  </div>`;
}

const ALLOWANCE_LABELS = { humanize: 'Humanizer runs', assignment: 'Assignment papers', presentation: 'Presentations', turnitin: 'Turnitin scans' };

async function loadBilling(force = false) {
  if (!state.signedIn || state.billingLoading || (state.billing && !force)) return;
  state.billingLoading = true;
  try {
    const res = await API.billing();
    state.billing = { plan: res.plan, payments: res.payments || [], subscription: res.subscription || null,
      provider: res.provider || 'cryptomus' };
    BOOT.plan = res.plan;
    const changed = CONFIG.billing.plan !== (res.plan ? res.plan.plan_id : null);
    CONFIG.billing.plan = res.plan ? res.plan.plan_id : null;
    if (changed) { renderSidebar(); applyLayout(); }
  } catch (err) {
    if (err.code === 'AUTH_REQUIRED') return onSignedOut();
    toast(err.message || 'Could not load billing');
  } finally {
    state.billingLoading = false;
  }
  if (currentRoute() === 'billing') render();
}

function renderBilling() {
  if (!state.signedIn) return `<div class="page">${pageHead(ITEMS.billing)}
    <section class="card earn-card"><div class="earn-guest"><p class="muted">Sign in to manage your plan and payments.</p>
      <button class="btn btn-primary" data-act="signup">Sign up</button></div></section></div>`;
  if (!state.billing) loadBilling();
  const B = CONFIG.billing, sp = state.billing ? state.billing.plan : BOOT.plan;
  const plan = sp && CONFIG.pricing.plans.find(x => x.id === sp.plan_id);
  const ends = sp ? fmtDate(String(sp.expires_at).slice(0, 10)) : '';
  const allowances = sp ? sp.allowances.map(a => `<li><span>${esc(ALLOWANCE_LABELS[a.feature] || a.feature)}</span>
      <span class="muted">${a.limit - a.used} of ${a.limit} left${a.window === 'day' ? ' today' : ''}</span></li>`).join('') : '';
  const sub = state.billing?.subscription, lemon = state.billing?.provider === 'lemon_squeezy';
  const portal = sub?.portal_url
    ? `<a class="btn btn-primary" href="${esc(sub.portal_url)}" target="_blank" rel="noopener">Manage subscription</a>` : '';
  const renews = sub?.renews_at ? fmtDate(String(sub.renews_at).slice(0, 10)) : ends;
  const left = sp ? `${sp.days_left} day${sp.days_left === 1 ? '' : 's'} left` : '';
  let status = ['Active', 'lvl-low'], note, actions;
  if (sub && sub.status === 'past_due') {
    status = ['Payment failed', 'lvl-high'];
    note = 'Your last renewal payment failed. Update your card in Manage subscription to keep the plan.';
    actions = portal;
  } else if (sub && sub.status === 'cancelled') {
    status = ['Cancelled', 'lvl-medium'];
    note = `Cancelled. The plan stays active until ${ends} (${left}). Resume any time in Manage subscription.`;
    actions = portal;
  } else if (sub) {
    note = `Renews on ${renews}. Cancel any time in Manage subscription; the plan stays active until the end of the paid month.`;
    actions = portal;
  } else {
    note = `Active until ${ends} (${left}). Pay again to add another month; nothing renews on its own.`;
    actions = `<a class="btn" href="#/pricing">Change plan</a>
      <button class="btn btn-primary" data-act="plan-pick" data-plan="${plan?.id}">Extend for a month</button>`;
  }
  const planCard = plan ? `
    <div class="bill-plan-top">
      <div>
        <p class="bill-plan-name">${esc(plan.name)} plan <span class="lvl ${status[1]}">${status[0]}</span></p>
        <p class="bill-price"><b>$${plan.price}</b> / month · ${fmtCr(plan.credits)} credits a month</p>
        <p class="muted small">${note}</p>
      </div>
    </div>
    ${allowances ? `<ul class="bill-allowances">${allowances}</ul>` : ''}
    <div class="bill-actions">${actions}</div>`
    : `<p class="bill-plan-name">Free plan</p><p class="muted small">No plan yet. Pick a plan to get monthly credits and free generations.</p>
       <div class="bill-actions"><a class="btn btn-primary" href="#/pricing">See plans</a></div>`;
  const payments = state.billing ? state.billing.payments : [];
  const rows = payments.length ? payments.map(h => `<tr>
          <td class="muted">${fmtDate(String(h.date).slice(0, 10))}</td><td>${esc(h.item)}</td><td>$${Number(h.amount).toFixed(2)}</td>
          <td><span class="lvl ${h.status === 'Paid' ? 'lvl-low' : 'lvl-medium'}">${esc(h.status)}</span></td>
        </tr>`).join('')
    : `<tr><td colspan="4" class="muted">${state.billing ? 'No payments yet.' : 'Loading…'}</td></tr>`;
  return `<div class="page account-page">
    ${pageHead(ITEMS.billing)}
    <div class="acc-grid">
      <section class="card acc-card" aria-labelledby="bill-plan-h">
        <h2 id="bill-plan-h">Current plan</h2>
        ${planCard}
      </section>
      <section class="card acc-card" aria-labelledby="bill-card-h">
        <h2 id="bill-card-h">Payment method</h2>
        <div class="bill-card">
          <span class="bill-card-ico" aria-hidden="true">${icon('card')}</span>
          ${lemon
            ? `<div><p><b>Card or PayPal via Lemon Squeezy</b></p><p class="muted small">Plans renew monthly; credits are one-time payments</p></div>`
            : `<div><p><b>Crypto via Cryptomus</b></p><p class="muted small">Each purchase is a one-time payment</p></div>`}
        </div>
        ${lemon && sub?.portal_url ? `<p><a class="acc-link" href="${esc(sub.portal_url)}" target="_blank" rel="noopener">Update payment method or download invoices</a></p>` : ''}
        <p class="muted small">${esc(lemon ? B.lemonNote : B.processorNote)}</p>
      </section>
    </div>
    <section class="card acc-card bill-history" aria-labelledby="bill-hist-h">
      <h2 id="bill-hist-h">Billing history</h2>
      <div class="table-wrap"><table class="hist bill-table">
        <thead><tr><th scope="col">Date</th><th scope="col">Description</th><th scope="col">Amount</th><th scope="col">Status</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </section>
  </div>`;
}

// Account information (Policies menu → Account), text from docmaxxing.com/account-info
function renderAccountInfo() {
  const u = CONFIG.user, I = u.info, list = (xs) => `<ul class="acc-info-list">${xs.map(x => `<li>${icon('check')}<span>${esc(x)}</span></li>`).join('')}</ul>`;
  return `<div class="page legal-page">
    <div class="legal-layout">
      ${infoNavHtml('account')}
      <article class="card legal-doc acc-info" aria-labelledby="legal-h">
        <header class="legal-head">
          <h1 id="legal-h">${esc(I.title)}</h1>
          <p class="lead">${esc(I.lead)}</p>
        </header>
        <div class="acc-info-cta">
          <p>${state.signedIn ? `You are signed in as <b>${esc(u.email)}</b>. Open account settings to edit your display name or password.`
            : 'Sign in to edit your display name or password.'}
            Buy credits from <a href="#/pricing">Pricing</a>, and invite friends from <a href="#/earn">Earn &amp; Share</a>.</p>
          ${state.signedIn ? `<a class="btn btn-primary" href="#/settings">${icon('gear')} Go to account settings</a>` : '<button class="btn btn-primary" data-act="signup">Sign up</button>'}
        </div>
        <div class="acc-info-grid">
          <div><h2>What your account unlocks</h2>${list(I.unlocks)}</div>
          <div><h2>What you can change in settings</h2>${list(I.change)}<p class="small muted">${esc(I.changeNote)}</p></div>
          <div><h2>Security tips</h2>${list(I.tips)}</div>
        </div>
      </article>
    </div>
  </div>`;
}

function bindAccount() {
  if (!state.signedIn) return;
  $('#acc-avatar-file').addEventListener('change', (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (!/^image\/(png|jpeg|webp)$/.test(f.type)) return toast('Please choose a PNG, JPG or WebP image');
    if (f.size > 2 * 1024 * 1024) return toast('The image is larger than 2 MB');
    API.account.avatar(f).then(res => {
      state.avatarUrl = res.avatar_url || null;
      if (BOOT.user) BOOT.user.avatarUrl = state.avatarUrl;
      renderSidebar(); render(); toast('Avatar updated');
    }).catch(err => toast(err.message || 'Could not upload the picture'));
  });
  $('#acc-profile-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const inp = $('#acc-name'), name = inp.value.trim();
    $('#acc-name-err').hidden = !!name; inp.setAttribute('aria-invalid', String(!name));
    if (!name) return inp.focus();
    API.account.profile(name).then(res => {
      CONFIG.user.name = res.name || name;
      if (BOOT.user) BOOT.user.name = CONFIG.user.name;
      renderSidebar(); renderHeader(); toast('Profile saved');
    }).catch(err => toast(err.message || 'Could not save your name'));
  });
  $('#acc-pw-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const cur = $('#acc-pw-cur'), nw = $('#acc-pw-new'), cf = $('#acc-pw-confirm'), err = $('#acc-pw-err');
    [cur, nw, cf].forEach(x => x.removeAttribute('aria-invalid'));
    const fail = (el, msg) => { err.textContent = msg; err.hidden = false; el.setAttribute('aria-invalid', 'true'); el.focus(); };
    if (!cur.value) return fail(cur, 'Enter your current password');
    if (nw.value.length < CONFIG.user.minPassword) return fail(nw, `The new password needs at least ${CONFIG.user.minPassword} characters`);
    if (nw.value !== cf.value) return fail(cf, 'The passwords do not match');
    err.hidden = true;
    const btn = $('#acc-pw-form [type=submit]');
    btn.disabled = true;
    API.account.password(cur.value, nw.value, cf.value).then(() => {
      e.target.reset(); toast('Password updated');
    }).catch(ex => fail(cur, ex.message || 'Could not update the password'))
      .finally(() => { btn.disabled = false; });
  });
}

/* ---------- Video tutorials (dialog) ---------- */
const tutDlg = $('#tut-dialog');
let tutCurrent = 0;

function tutPanelHtml(t) {
  const video = t.youtubeId
    ? `<iframe src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(t.youtubeId)}" title="${esc(t.label)} video"
         allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen" allowfullscreen loading="lazy"></iframe>`
    : `<div class="tut-poster" role="img" aria-label="Video coming soon">
         <span class="tut-play" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z"/></svg></span>
         <span class="tut-soon">Video coming soon</span></div>`;
  return `<div class="tut-video">${video}</div>
    <h3 class="tut-h">${esc(t.label)}</h3>
    <p class="tut-desc">${esc(t.description)}</p>
    <div class="tut-actions">
      ${t.tour ? `<button class="btn btn-sm" data-act="tut-tour" data-tour-name="${t.tour}">${icon('help')} Take the interactive tour</button>` : ''}
      ${t.youtubeId ? `<a class="btn btn-sm btn-ghost" href="https://www.youtube.com/watch?v=${encodeURIComponent(t.youtubeId)}" target="_blank" rel="noopener">Open on YouTube</a>` : ''}
    </div>`;
}

function renderTutorials() {
  const T = CONFIG.tutorials;
  tutDlg.innerHTML = `
    <div class="tut-head">
      <h2 id="tut-title">${esc(T.title)}</h2>
      <button class="icon-btn" type="button" data-act="tut-close" aria-label="Close">${icon('close')}</button>
    </div>
    <div class="tut-body">
      <div class="tut-list" role="tablist" aria-orientation="vertical" aria-label="Topics">
        ${T.items.map((t, i) => `<button type="button" role="tab" class="tut-tab" id="tut-tab-${i}" aria-controls="tut-panel"
          aria-selected="${i === tutCurrent}" tabindex="${i === tutCurrent ? 0 : -1}" data-act="tut-pick" data-index="${i}">${esc(t.label)}</button>`).join('')}
      </div>
      <div class="tut-panel" id="tut-panel" role="tabpanel" aria-labelledby="tut-tab-${tutCurrent}">${tutPanelHtml(T.items[tutCurrent])}</div>
    </div>`;
}

function openTutorials() {
  // Start on the tutorial for the page you are on, if there is one
  const here = ALL_ITEMS.find(i => i.route === currentRoute())?.id;
  const idx = CONFIG.tutorials.items.findIndex(t => t.id === here);
  tutCurrent = idx >= 0 ? idx : 0;
  hideTip();
  renderTutorials();
  tutDlg.showModal();
  $(`#tut-tab-${tutCurrent}`).focus();
}

function pickTutorial(i, focus = true) {
  tutCurrent = (i + CONFIG.tutorials.items.length) % CONFIG.tutorials.items.length;
  renderTutorials();
  if (focus) $(`#tut-tab-${tutCurrent}`).focus();
}

tutDlg.addEventListener('keydown', (e) => {
  if (!e.target.matches('.tut-tab')) return;
  const keys = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
  if (keys[e.key]) { e.preventDefault(); pickTutorial(tutCurrent + keys[e.key]); }
  else if (e.key === 'Home') { e.preventDefault(); pickTutorial(0); }
  else if (e.key === 'End') { e.preventDefault(); pickTutorial(CONFIG.tutorials.items.length - 1); }
});
// Click on the dark backdrop closes the dialog
tutDlg.addEventListener('click', (e) => { if (e.target === tutDlg) tutDlg.close(); });
tutDlg.addEventListener('close', () => { tutDlg.innerHTML = ''; });   // stops a playing video

/* ---------- Help ---------- */
function renderHelp() {
  const C = CONFIG.help;
  return `<div class="page help-page">
    ${pageHead(ITEMS.help, '', `<button class="btn btn-sm" data-act="open-tutorials" aria-haspopup="dialog">${icon('video')} Watch tutorials</button>`)}
    <section class="card help-contact" aria-labelledby="help-h">
      <form class="help-form" id="help-form" novalidate>
        <h2 id="help-h">${esc(C.formTitle)}</h2>
        <p class="muted">${esc(C.formLead)}</p>
        <div class="help-fields">
          <label class="field" for="help-topic"><span>Topic</span>
            <select class="select" id="help-topic" name="topic">${C.topics.map(t => `<option>${esc(t)}</option>`).join('')}</select></label>
          <label class="field" for="help-email"><span>Your email</span>
            <input class="field-input" id="help-email" name="email" type="email" autocomplete="email" required placeholder="you@university.edu" value="${state.signedIn ? esc(CONFIG.user.email) : ''}" aria-describedby="help-email-err">
            <span class="field-err" id="help-email-err" hidden>Enter an email so we can reply</span></label>
          <label class="field field-wide" for="help-msg"><span>Message</span>
            <textarea class="field-input" id="help-msg" name="message" rows="5" required placeholder="What happened? Add the document name or a link if it helps." aria-describedby="help-msg-err"></textarea>
            <span class="field-err" id="help-msg-err" hidden>Write a short message</span></label>
        </div>
        <div class="help-form-row">
          <button type="submit" class="btn btn-primary">${icon('send')} Send message</button>
        </div>
      </form>
    </section>

  </div>
  ${landFooterHtml({ inApp: true })}`;
}

function bindHelp() {
  const form = $('#help-form');
  const check = (el, errId) => { const bad = !el.value.trim() || (el.type === 'email' && !el.checkValidity()); $('#' + errId).hidden = !bad; el.setAttribute('aria-invalid', String(bad)); return !bad; };
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const okEmail = check($('#help-email'), 'help-email-err'), okMsg = check($('#help-msg'), 'help-msg-err');
    if (!okEmail) return $('#help-email').focus();
    if (!okMsg) return $('#help-msg').focus();
    const topic = $('#help-topic').value, email = $('#help-email').value.trim(), message = $('#help-msg').value.trim();
    const btn = $('#help-form [type=submit]');
    btn.disabled = true;
    const send = state.signedIn
      ? API.feedback(`[Help form] ${topic}\nReply to: ${email}\n\n${message}`)
      : API.contact({ topic, email, message });
    send.then(() => { form.reset(); toast(CONFIG.help.sentToast); })
      .catch(err => toast(err.message || 'Could not send. Email ' + CONFIG.help.email))
      .finally(() => { btn.disabled = false; });
  });
}

/* ---------- Stubs for other tools ---------- */
function renderStub(item) {
  return `<div class="page">
    ${pageHead(item, '<span class="stub-tag">prototype stub</span>')}
    <section class="card">
      <div class="placeholder">${esc(item.label)} workspace goes here.<br><span class="small">Cost: ${costHtml(item)}</span></div>
    </section>
  </div>`;
}

/* =========================================================
   Page events
   ========================================================= */
function bindPage(id) {
  if (id === 'home') bindHome();
  if (id === 'pricing') bindPricing();
  if (id.startsWith('admin')) bindAdmin();
  if (id === 'help') bindHelp();
  if (id === 'settings') bindAccount();
  // Phones: the policy list scrolls sideways, so bring the open document into view
  if (ITEMS[id]?.legal) $('.legal-nav [aria-current="page"]')?.scrollIntoView({ block: 'nearest', inline: 'center' });
  if (id === 'humanizer') {
    bindTextTool(id);
    const t = toolState(id);
    if (t.autoRun) { t.autoRun = false; runTool(id); }
  }
  if (id === 'turnitin') {
    bindScan();
    const t = toolState('turnitin');
    if (t.autoRun && state.signedIn) { t.autoRun = false; runScan(); }
  }
  if (id === 'assignment') bindAssignment();
  if (id === 'workspace') bindEditor();
  if (id === 'presentation') bindSlides();
  if (id === 'format') bindFormat();
  if (id === 'check') bindReview();
}

function rerenderDocs() {
  const sec = $('#home-history');
  if (!sec) return;
  sec.innerHTML = historyHtml();
  $('#doc-filter')?.addEventListener('change', (e) => { state.docFilter = e.target.value; rerenderDocs(); });
}

function bindTextTool(id) {
  const t = toolState(id), item = ITEMS[id];
  const ta = $('#tool-text'), runBtn = $('#run-btn'), counter = $('#counter');

  function refresh() {
    const words = countWords(t.text), over = words > CONFIG.wordLimit;
    counter.textContent = `${fmtNum(words)} / ${fmtNum(CONFIG.wordLimit)} words${over ? ' — too long' : ''}`;
    counter.classList.toggle('over', over);
    const guestOut = !state.signedIn && item.guestPrice && state.guestRunsUsed >= 1;
    runBtn.innerHTML = guestOut ? 'Sign up to continue' : `${icon('sparkles')} ${esc(CONFIG.flows[id].runLabel)}`;
    runBtn.disabled = !guestOut && (!words || over || t.status === 'loading');
  }
  refresh();

  // Emptying the field drops the uploaded file, so newly pasted text gets plain Copy, not the file download menu
  ta.addEventListener('input', () => { t.text = ta.value; if (!t.text.trim()) t.fileName = ''; refresh(); });

  // Tabs: click + arrow keys
  const tabs = $$('[role="tab"]');
  const setMode = (mode) => { t.mode = mode; render(); $(`[data-mode="${mode}"]`).focus(); };
  tabs.forEach(tab => {
    tab.addEventListener('click', () => setMode(tab.dataset.mode));
    tab.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') setMode(t.mode === 'paste' ? 'file' : 'paste');
    });
  });

  // File upload: the text is extracted on the server (.docx, .pdf) or read here (.txt)
  const dz = $('#dropzone'), input = $('#file-input');
  const takeFile = (file) => {
    if (!file) return;
    if (!/\.(docx|pdf|txt)$/i.test(file.name)) { toast('Please choose a .docx, .pdf or .txt file'); return; }
    t.fileName = file.name; t.note = 'Reading your file…';
    render();
    API.extractText(file).then((text) => {
      text = text.trim();
      if (!text) throw new Error('No readable text found in that file.');
      Object.assign(t, { text, mode: 'paste', note: '' });
      toast(`File “${file.name}” added`);
    }).catch((err) => {
      Object.assign(t, { fileName: '', note: err.message || 'Could not read the uploaded file.' });
    }).finally(() => { if (currentRoute() === item.route) render(); });
  };
  dz.addEventListener('click', () => input.click());
  input.addEventListener('change', () => takeFile(input.files[0]));
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
  dz.addEventListener('drop', (e) => { e.preventDefault(); dz.classList.remove('drag'); takeFile(e.dataTransfer.files[0]); });
}

async function runTool(id) {
  const t = toolState(id), item = ITEMS[id];
  if (!state.signedIn && item.guestPrice && state.guestRunsUsed >= 1) return signUp();
  if (t.status === 'loading') return;
  const onPage = () => currentRoute() === item.route;
  t.status = 'loading'; t.result = null; t.error = null;
  if (onPage()) { $('#result').innerHTML = resultHtml(id); $('#run-btn').disabled = true; }
  const source = t.text;
  try {
    const data = await API.humanize(source);
    const out = String(data.humanized_text || data.text || '').trim();
    if (!out) throw new API.ApiError('The humanizer returned an empty result. Try again.', { code: 'EMPTY' });
    t.status = 'done'; t.result = { text: out, file: t.fileName || '' };
    if (!state.signedIn) state.guestRunsUsed = data.free_runs_left === 0 ? 1 : 0;
    if (state.signedIn) { addDoc(source, id, { text: out }); loadCredits(); }
  } catch (err) {
    const e = apiErrorInfo(err, { intent: id });
    if (err.code === 'REGISTER_REQUIRED') state.guestRunsUsed = 1;
    t.status = e.handled ? 'idle' : 'error';
    t.error = e;
  }
  if (onPage()) { render(); $('#result .btn-primary')?.focus(); }
}

function addDoc(text, tool, extra = {}) {
  const title = text.trim().split(/\s+/).slice(0, 6).join(' ') + '…';
  state.docs.unshift({ id: 'd' + Date.now(), title, tool, date: todayIso(), ...extra });
  saveDocs();
}

/* One place that turns API errors into what the user sees. `handled` = we already
   opened the sign-up dialog or moved to another page. */
function apiErrorInfo(err, { intent } = {}) {
  const code = err && err.code, data = (err && err.data) || {};
  switch (code) {
    case 'REGISTER_REQUIRED':
    case 'AUTH_REQUIRED':
      if (code === 'AUTH_REQUIRED' && state.signedIn) onSignedOut();
      openSignup({ intent, lead: err.message || `Create a free account to continue. You get ${CONFIG.signupCredits} credits.` });
      return { handled: true, message: err.message };
    case 'EMAIL_NOT_VERIFIED':
      location.href = '/verify-email/code';
      return { handled: true, message: 'Confirm your email to continue.' };
    case 'INSUFFICIENT_COINS': {
      const need = data.required ?? data.cost, have = data.balance ?? state.balance;
      return { message: need != null ? `Not enough credits: this needs ${need}, you have ${have}.` : 'Not enough credits for this run.', action: 'topup' };
    }
    case 'LOGIN_REQUIRED':
      return { message: 'The humanizer service is temporarily unavailable. Your credits weren’t charged. Try again in a few minutes.' };
    case 'NO_CHANGE':
      return { message: 'The text came back unchanged, often because of a daily limit. Try again later.' };
    default:
      return { message: (err && err.message) || 'Something went wrong. Try again.' };
  }
}

function clearTool(id) {
  state.tools[id] = { mode: toolState(id).mode, text: '', fileName: '', status: 'idle', result: null, note: '' };
  render();
  $('#tool-text')?.focus();
}

// Download the result under the uploaded file's name: "My essay-humanized.pdf"
async function downloadResult(id, ext) {
  $('.dl-wrap')?.classList.remove('is-open');
  const r = toolState(id).result;
  if (!r) return;
  const base = (r.file || 'text').replace(/\.[^.]+$/, '') + '-humanized', name = `${base}.${ext}`;
  let blob;
  try {
    blob = ext === 'txt' ? new Blob([r.text], { type: 'text/plain;charset=utf-8' }) : await API.exportText(r.text, base, ext);
  } catch (err) {
    toast(err.message || 'Could not download. Try again.');
    return;
  }
  const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name });
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  toast(`Downloaded “${name}”`);
}

function handOff(fromId) {
  const t = toolState(fromId), flow = CONFIG.flows[fromId];
  const text = fromId === 'humanizer' ? t.result.text : t.text;
  const target = toolState(flow.next.to);
  if (flow.next.to === 'turnitin') {
    Object.assign(state.qd, { text, status: 'idle', result: null, error: '', autoRun: true,
      note: `Your text from ${ITEMS[fromId].label}, checked with ${CONFIG.detector.switch.quick.title}.` });
    state.detMode = 'quick';
    go(ITEMS.turnitin.route);
    return;
  }
  Object.assign(target, { mode: 'paste', text, status: 'idle', result: null, fileName: '',
    note: `Text added from ${ITEMS[fromId].label}.`, fromHumanizer: fromId === 'humanizer' });
  go(ITEMS[flow.next.to].route);
}

function copyResult() {
  const text = $('#result-text')?.textContent || '';
  const done = () => toast('Copied to clipboard');
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done, fallback);
  else fallback();
  function fallback() {
    const ta = Object.assign(document.createElement('textarea'), { value: text });
    document.body.append(ta); ta.select();
    try { document.execCommand('copy'); done(); } catch { toast('Copy failed'); }
    ta.remove();
  }
}

/* ---------- Confirmation dialog (delete document / delete check) ---------- */
const dlg = $('#confirm-dialog');
let confirmAction = null, confirmOpener = null;
// onOk runs the action and may return an element to focus afterwards
function askConfirm({ title, text, okLabel = 'Delete', onOk, opener }) {
  confirmAction = onOk; confirmOpener = opener;
  $('#confirm-title').textContent = title;
  $('#confirm-text').textContent = text;
  $('#confirm-ok').textContent = okLabel;
  dlg.showModal();
  $('#confirm-cancel').focus();
}
function askDelete(docId, opener) {
  const doc = state.docs.find(d => d.id === docId);
  askConfirm({
    title: 'Delete document?', opener,
    text: `“${doc.title}” will be removed from your documents. This can’t be undone.`,
    onOk: () => {
      state.docs = state.docs.filter(d => d.id !== docId);
      saveDocs();
      if (!state.docs.some(d => d.tool === state.docFilter)) state.docFilter = 'all';
      rerenderDocs();
      toast(`Deleted “${doc.title}”`);
      return $('.doc-list [data-act="delete-doc"]') || $('#docs-h');
    },
  });
}
$('#confirm-cancel').addEventListener('click', () => dlg.close());
$('#confirm-ok').addEventListener('click', () => {
  const action = confirmAction;
  confirmAction = null; confirmOpener = null;   // the opener is gone after a delete
  dlg.close();
  action?.()?.focus();
});
dlg.addEventListener('close', () => { if (confirmOpener && document.contains(confirmOpener)) confirmOpener.focus(); confirmOpener = null; });


/* =========================================================
   Public flow: Landing → Sign up (dialog) → Home (dashboard)
   ========================================================= */
const PUBLIC_ROUTES = ['landing'];
const TASK_ITEMS = () => ALL_ITEMS.filter(i => i.id !== 'home' && !i.info && !i.hidden);

function navigate(route) {
  if (location.hash === '#/' + route) render(); else go(route);
}

function publicNav(right) {
  return `<header class="pub-nav">
    <a class="logo" href="#/landing"><span class="logo-mark">${LOGO_SVG}</span><span>${esc(CONFIG.brand)}</span></a>
    ${right}
    ${themeBtnHtml()}
  </header>`;
}

function priceLabel(item) {
  if (item.free) return '<span class="badge">Free</span>';
  return `<span class="tag">${esc(item.price || CONFIG.pricePlaceholder)}</span>`;
}

/* ---------- Landing ---------- */
let landScrollBound = false;
function bindLanding() {
  const update = () => {
    $('.land .pub-nav')?.classList.toggle('is-floating', scrollY > 24);
    const hero = $('.land-hero');
    if (!hero) return;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const p = reduce ? 1 : Math.min(1, Math.max(0, scrollY / (innerHeight * .55)));
    hero.style.setProperty('--p', p.toFixed(3));
  };
  update();
  revealLanding();
  bindHeroVideo();
  if (landScrollBound) return;
  landScrollBound = true;
  let queued = false;
  addEventListener('scroll', () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; update(); });
  }, { passive: true });
  addEventListener('resize', update);
}

// Hero demo video: starts when at least a third of it is on screen, pauses when it leaves; the still stays for reduced motion
function bindHeroVideo() {
  const v = $('.land-product-video');
  if (!v || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  v.addEventListener('playing', () => v.classList.add('is-on'), { once: true });
  new IntersectionObserver(([e]) => {
    if (!v.isConnected) return;
    if (e.isIntersecting) v.play().catch(() => {});
    else v.pause();
  }, { threshold: .35 }).observe(v);
}

// Scroll reveal, as on Framer sites: blocks fade up out of a soft blur when they enter the view; siblings stagger
// One review: a Telegram-style chat (all cards the same height, newest at the bottom) and the student's words in English
function reviewHtml(r) {
  const bubble = (m) => `<div class="tg-msg ${m.me ? 'me' : ''}">${m.file
    ? `<span class="tg-file"><i>${icon('file')}</i><span><b>${esc(m.file)}</b><small>${esc(m.size)}</small></span></span>`
    : esc(m.text)}<span class="tg-time">${esc(m.time)}${m.me ? ' ✓✓' : ''}</span>${m.react ? `<span class="tg-react">${m.react}</span>` : ''}</div>`;
  return `<figure class="land-review">
    <div class="tg-chat" aria-hidden="true"><div class="tg-msgs">${r.msgs.map(bubble).join('')}</div></div>
    <figcaption><q>${esc(r.quote)}</q><span>${esc(r.tag)}</span></figcaption>
  </figure>`;
}
const REVEAL = ['.land-stats li', '.pub-sec > h2', '.pub-sec > h2 + .muted', '.land-steps > li', '.bento-tile', '.land-video', '.land-veil-text > *', '.land-veil > .veil-demo',
  '.land-plans .plan', '.land-review', '.pub-sec-center > .btn', '.land-faq details', '.land-final-text > *', '.land-final-shot', '.lf-top > *', '.lf-word'];
function revealLanding() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((entries) => entries.forEach(e => {
    if (!e.isIntersecting) return;
    const el = e.target;
    io.unobserve(el);
    el.classList.add('rv-in');
    // Drop the helper classes once played, so hover transitions on cards work as before
    setTimeout(() => el.classList.remove('rv', 'rv-in'), 1100 + (+el.style.getPropertyValue('--rv-i') || 0) * 90);
  }), { threshold: .12, rootMargin: '0px 0px -6% 0px' });
  $$(REVEAL.join(',')).forEach(el => {
    const sibs = [...el.parentElement.children].filter(c => c.matches(REVEAL.join(',')));
    el.style.setProperty('--rv-i', Math.min(sibs.indexOf(el), 6));
    el.classList.add('rv');
    io.observe(el);
  });
}
function landNavHtml() {
  return publicNav(`<nav class="pub-links" aria-label="Landing sections">
      ${CONFIG.landing.nav.map(([id, label]) => `<a href="#/landing" data-act="scroll-to" data-target="${id}">${esc(label)}</a>`).join('')}
    </nav>
    <button class="btn btn-ghost" data-act="open-login">Log in</button>
    <button class="btn btn-primary" data-act="signup">Start free</button>`);
}

// Policies, About, FAQ… for visitors without an account: the landing header and footer around the document

// Links into the app from the landing: every tool opens directly, guests included
const appLinkAttrs = (item) => `href="${esc(itemHref(item))}" ${itemLinkAttrs(item)}`;

function renderLanding() {
  const L = CONFIG.landing, P = CONFIG.pricing;
  const sec = (id, title, sub, body, cls = '') => `<section class="pub-sec ${cls}" id="${id}" aria-labelledby="${id}-h">
      <h2 id="${id}-h">${esc(title)}</h2>${sub ? `<p class="muted">${esc(sub)}</p>` : ''}${body}</section>`;
  // Bento grid: each tile gets a tone (blue / navy / black / white / sky) and a small illustration
  const BENTO = [
    ['turnitin', 'ai', 'blue', `<span class="bt-ai-art"><span class="bt-doc"><span class="bt-doc-head">${icon('file')}<span>Climate policy essay.docx</span></span>
      <span class="bt-doc-text"><mark class="ai">It is important to note that climate policy plays a crucial role in shaping our shared future.</mark> Last summer our town ran out of water for two weeks, and that changed how I think about it. <mark class="ai">Furthermore, governments must leverage innovative and sustainable solutions.</mark> <mark class="mix">Carbon taxes are one option,</mark> but they hit poorer families hardest.</span>
      <span class="bt-doc-legend"><span><i class="ai"></i>Likely AI</span><span><i class="mix"></i>Mixed</span><span><i></i>Human</span></span></span>
      <span class="bt-card"><span class="bt-row"><span>AI score</span><b>76%</b></span><span class="bt-bar"><i style="width: 76%"></i></span>
      <span class="bt-row"><span>Plagiarism</span><b>9%</b></span><span class="bt-bar"><i style="width: 9%"></i></span></span></span>`],
    ['humanizer', 'hum', 'black', `<span class="bt-swap"><s>It is imperative to note that…</s><span>Here’s the thing…</span></span>`],
    ['veil', 'veil', 'navy', `<span class="bt-veil-art"><span class="bt-page"><span class="bt-page-bar"><i></i><i></i><i></i><span>Biology 101 · Week 4</span></span>
      <span class="bt-page-text">The Krebs cycle runs in the mitochondrial matrix. <mark>It produces NADH and FADH₂</mark>, which feed the electron transport chain.</span>
      <span class="bt-page-lines"><i></i><i></i><i></i></span></span>
      <span class="bt-pop"><span class="bt-pop-head">${icon('sparkles')}Veil</span>They carry electrons to the transport chain, where most of the cell’s ATP is made.</span></span>
      <span class="bt-keys">${kbd('Q')}<span>Ask about anything you select</span></span>`],
    ['format', 'fmt', 'white', `<span class="bt-chips">${['APA', 'MLA', 'Harvard', 'Chicago'].map(c => `<span>${c}</span>`).join('')}</span>`],
    ['assignment', 'asg', 'sky', `<span class="bt-bubble">Write 1,500 words on climate policy</span>`],
    ['workspace', 'edt', 'white', `<span class="bt-lines"><i></i><i class="hl"></i><i></i></span>`],
    ['presentation', 'sld', 'black', `<span class="bt-slides"><i></i><i></i><i></i></span>`],
    ['check', 'rev', 'blue2', `<span class="bt-checks">${['Matches the brief', 'Sources cited'].map(c => `<span>${icon('check')}${c}</span>`).join('')}</span>`],
  ];
  const tools = BENTO.map(([id, area, tone, art]) => {
    const it = ITEMS[id];
    return `<a class="bento-tile bt-${area} tone-${tone}" ${appLinkAttrs(it)}>
      <span class="bt-head"><span class="bt-icon">${icon(it.icon)}</span>${it.free ? '<span class="bt-free">Free</span>' : ''}</span>
      <b class="bt-title">${esc(it.label)}</b>
      <span class="bt-text">${esc(it.description)}</span>
      <span class="bt-art" aria-hidden="true">${art}</span>
    </a>`;
  }).join('');
  return `<div class="pub land">
    ${landNavHtml()}

    <section class="land-hero" aria-labelledby="hero-h">
      <div class="land-hero-text">
        <h1 class="hero-title" id="hero-h">${esc(L.title)}</h1>
        <p class="hero-sub">${esc(L.subtitle)}</p>
        <div class="hero-cta">
          <button class="btn btn-primary btn-lg" data-act="signup">${esc(L.cta)}</button>
          ${state.signedIn ? '' : `<a class="btn btn-lg" href="#/home">${esc(L.secondaryCta)}</a>`}
        </div>
      </div>
      <div class="land-product">
        <div class="land-product-frame"><img src="${LANDING_SHOTS.dashboard}" alt="The DocMaxxing dashboard: paste a text, check it for AI or humanize it, and see your credit and document history" width="1800" height="1125">
          <video class="land-product-video" src="${LANDING_MEDIA}ai-detector.mp4" muted loop playsinline preload="metadata" aria-hidden="true" tabindex="-1"></video></div>
      </div>
    </section>

    <ul class="land-stats" aria-label="DocMaxxing in numbers">${L.stats.map(([n, t, ic]) => `<li><i class="land-stat-ic" aria-hidden="true"><svg viewBox="-5 -5 34 34"><g class="stk-bg">${ICONS[ic]}</g><g class="stk-fg">${ICONS[ic]}</g></svg></i><b>${esc(n)}</b><span>${esc(t)}</span></li>`).join('')}</ul>

    ${sec('how', L.howTitle, '', `<ol class="land-steps">${L.steps.map((s, i) => `<li class="card">
        <div class="land-step-text"><span class="land-step-n">Step ${i + 1}</span>
        <h3>${esc(s.title)}</h3><p class="muted">${esc(s.text)}</p></div>
        <div class="land-shot-frame"><img src="${LANDING_SHOTS[s.shot]}" alt="" loading="lazy"></div></li>`).join('')}</ol>`)}

    ${sec('tools', L.toolsTitle, L.toolsSub, `<div class="bento">${tools}</div>`)}

    ${sec('video', L.videoTitle, L.videoText, `<button class="land-video" type="button" data-act="intro-play" aria-label="Play the overview video">
        <span class="tut-play" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z"/></svg></span><span class="intro-len">2:00</span></button>`, 'pub-sec-center')}

    <section class="land-veil" id="veil-land" aria-labelledby="veil-land-h">
      <div class="land-veil-text">
        <span class="land-eyebrow">${icon('chrome')} Browser extension</span>
        <h2 id="veil-land-h">${esc(L.veilTitle)}</h2>
        <p class="muted">${esc(L.veilText)}</p>
        <ul class="land-veil-sites" aria-label="Works in">${['Google Docs', 'Canvas', 'Moodle', 'Word Online'].map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <div class="veil-cta"><button class="btn btn-lg land-veil-btn" data-act="signup">${icon('chrome')} Get Veil</button></div>
      </div>
      ${veilDemoHtml()}
    </section>

    ${sec('pricing-land', L.pricingTitle, L.pricingSub, `<div class="plans land-plans">${P.plans.map(p => planHtml(p, { compact: true })).join('')}</div>`)}

    ${sec('reviews', L.reviewsTitle, L.reviewsSub, `<div class="land-reviews">${L.reviews.map(reviewHtml).join('')}</div>
      <a class="btn" href="${esc(L.reviewsUrl)}" target="_blank" rel="noopener">${icon('telegram')} See all in Telegram</a>`, 'pub-sec-center')}

    ${sec('faq', L.faqTitle, '', `<div class="land-faq">${L.faq.map(([q, a]) => `<details class="card"><summary><span>${esc(q)}</span><span class="faq-sign" aria-hidden="true"></span></summary><p class="muted">${esc(a)}</p></details>`).join('')}</div>`, 'pub-sec-center')}

    <section class="land-final" aria-labelledby="final-h">
      <div class="land-final-text">
        <h2 id="final-h">${esc(L.finalTitle)}</h2>
        <p class="muted">${esc(L.finalText)}</p>
        <button class="btn btn-primary btn-lg" data-act="signup">${esc(L.cta)}</button>
      </div>
      <div class="land-final-shot"><img src="${LANDING_SHOTS.check}" alt="An AI Detector result: the AI score and the parts that look AI-written" loading="lazy"></div>
    </section>

    ${landFooterHtml()}
  </div>`;
}

// Site footer (landing, public documents, Help): brand + socials, link columns, big wordmark

// Site footer (landing, Help): brand + socials, link columns, big wordmark
function landFooterHtml({ inApp = false } = {}) {
  const C = CONFIG.help, F = C.footer;
  // On the landing every link is a real page (crawlable); inside the app policies open as app pages
  const link = (l) => {
    const id = l.path === '/account-info' ? 'account' : l.path.slice(1);
    if (id === 'account') return state.signedIn ? `<a href="#/account">${esc(l.label)}</a>` : `<a href="#/landing" data-act="open-login">${esc(l.label)}</a>`;
    if (!inApp) return `<a href="${esc(l.path)}">${esc(l.label)}</a>`;
    if (CONFIG.legal.some(d => d.id === id)) return `<a href="#/${id}">${esc(l.label)}</a>`;
    if (id === 'contact') return `<a href="#/help">${esc(l.label)}</a>`;
    return `<a href="${esc(C.site + l.path)}" target="_blank" rel="noopener">${esc(l.label)}</a>`;
  };
  const toolLink = (i) => inApp || i.url ? `<a ${appLinkAttrs(i)}>${esc(i.label)}</a>` : `<a href="/${i.route === 'format' ? 'formatter' : i.route}">${esc(i.label)}</a>`;
  const extra = inApp
    ? `<a href="${esc(C.site)}/blog" target="_blank" rel="noopener">Blog</a><a href="#/pricing">Pricing</a>`
    : '<a href="/blog">Blog</a><a href="/pricing">Pricing</a>';
  const legal = ['/privacy', '/terms', '/disclaimer', '/payment-policy', '/delivery-policy', '/refund-policy'];
  const col = (title, html) => `<nav class="lf-col" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}</nav>`;
  return `<footer class="land-foot${inApp ? ' in-app' : ''}">
    <div class="lf-top">
      <div class="lf-brand">
        <a class="logo" href="#/landing"><span class="logo-mark">${LOGO_SVG}</span><span>${esc(CONFIG.brand)}</span></a>
        <p class="muted">Academic formatting, humanizing and integrity tools for students.</p>
        <div class="if-socials">${F.socials.map(x => `<a class="if-social app-tile app-${x.icon}" href="${esc(x.url)}" ${x.url.startsWith('mailto') ? '' : 'target="_blank" rel="noopener"'} aria-label="${esc(x.label)}">${appIcon(x.icon)}</a>`).join('')}</div>
      </div>
      ${col('Tools', [...TASK_ITEMS(), ITEMS.veil].map(toolLink).join(''))}
      ${col('Company', F.links.filter(l => !legal.includes(l.path)).map(link).join('') + extra)}
      ${col('Legal', F.links.filter(l => legal.includes(l.path)).map(link).join(''))}
      ${col('Support', `<a href="mailto:${esc(C.email)}">${esc(C.email)}</a><a href="https://wa.me/${C.phone.replace(/\D/g, '')}" target="_blank" rel="noopener">${esc(C.phone)}</a><span class="muted">${esc(C.hours)}</span>`)}
    </div>
    <p class="lf-word" aria-hidden="true">${esc(CONFIG.brand)}</p>
  </footer>`;
}

/* ---------- Sign up / Log in dialog ---------- */


const signupDlg = $('#signup-dialog');
let signupOpener = null;

function openSignup({ intent, mode = 'signup', title, lead } = {}) {
  if (intent) state.intent = intent;
  const item = state.intent && ITEMS[state.intent];
  const isLogin = mode === 'login';
  signupOpener = document.activeElement;
  signupDlg.innerHTML = `<form method="dialog" id="signup-form" novalidate>
    <div class="dlg-head">
      <h2 id="signup-title">${isLogin ? 'Log in' : esc(title || 'Create your account')}</h2>
      <button type="button" class="icon-btn" data-act="close-signup" aria-label="Close">${icon('close')}</button>
    </div>
    <p class="muted" style="margin-top:0">${isLogin ? 'Welcome back.'
      : lead ? esc(lead)
      : item ? `You picked <b>${esc(item.label)}</b>. We’ll take you there after three quick questions.`
      : 'Three quick questions after this, then you’re in.'}</p>
    ${isLogin ? '' : `<ul class="perks">${CONFIG.signup.perks.map(p => `<li>${icon('check')}${esc(p)}</li>`).join('')}</ul>`}
    <label class="field" for="signup-email"><span>Email</span>
      <input class="input field-input" id="signup-email" type="email" autocomplete="email" placeholder="you@university.edu" aria-describedby="signup-error"></label>
    <label class="field" for="signup-password" style="margin-top:12px"><span>Password</span>
      <input class="input field-input" id="signup-password" type="password" autocomplete="${isLogin ? 'current-password' : 'new-password'}"
        placeholder="${isLogin ? 'Your password' : `At least ${CONFIG.user.minPassword} characters`}" aria-describedby="signup-error"></label>
    ${isLogin ? '' : `<label class="field" for="signup-password2" style="margin-top:12px"><span>Repeat password</span>
      <input class="input field-input" id="signup-password2" type="password" autocomplete="new-password" aria-describedby="signup-error"></label>`}
    <p class="small" id="signup-error" role="alert" hidden></p>
    <button type="submit" class="btn btn-primary btn-block" style="margin-top:12px" data-mode="${mode}">${isLogin ? 'Log in' : 'Create account'}</button>
    <p class="small muted" style="text-align:center;margin:12px 0 0">${isLogin
      ? 'New here? <button type="button" class="link-btn" data-act="signup">Create an account</button>'
      : 'Already have an account? <button type="button" class="link-btn" data-act="open-login">Log in</button>'}</p>
  </form>`;
  $('#signup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = $('#signup-email'), pw = $('#signup-password'), pw2 = $('#signup-password2');
    const fail = (input, msg) => {
      const err = $('#signup-error'); err.hidden = false; err.textContent = msg;
      $$('#signup-form [aria-invalid]').forEach(x => x.removeAttribute('aria-invalid'));
      if (input) { input.setAttribute('aria-invalid', 'true'); input.focus(); }
    };
    if (!/^\S+@\S+\.\S+$/.test(email.value)) return fail(email, 'Enter an email like you@university.edu');
    if (!pw.value) return fail(pw, 'Enter your password');
    if (!isLogin && pw.value.length < CONFIG.user.minPassword) return fail(pw, `Use at least ${CONFIG.user.minPassword} characters`);
    if (pw2 && pw2.value !== pw.value) return fail(pw2, 'Passwords do not match');
    const btn = $('#signup-form [type=submit]'), label = btn.textContent;
    btn.disabled = true; btn.textContent = 'Please wait…';
    try {
      const data = isLogin
        ? await API.login(email.value.trim(), pw.value)
        : await API.register({ email: email.value.trim(), password: pw.value, passwordConfirm: pw2.value });
      finishSignup(mode, data);
    } catch (err) {
      btn.disabled = false; btn.textContent = label;
      fail(null, err.message || 'Something went wrong. Please try again.');
    }
  });
  if (!signupDlg.open) signupDlg.showModal();
  $('#signup-email').focus();
  syncProto();
}

function finishSignup(mode, data) {
  const u = data.user;
  BOOT.user = { id: u.id, email: u.email, name: u.name || u.email.split('@')[0], isVerified: !!u.is_verified,
    avatarUrl: u.avatar_file ? '/static/' + u.avatar_file : null, isAdmin: !!u.is_admin };
  if (mode !== 'login') {
    store.set(introKey(), false);
    state.profile = state.intent ? { intent: state.intent } : null;   // the tool picked on the landing page (used by "Take the tour")
    store.set('profile', state.profile);
  }
  if (data.email_verification_required) {
    // The code screen lives on the old site; it brings the user back here when done
    location.href = '/verify-email/code';
    return;
  }
  signupDlg.close();
  Object.assign(CONFIG.user, { name: BOOT.user.name, email: u.email, id: '#' + u.id, isAdmin: BOOT.user.isAdmin });
  Object.assign(state, {
    signedIn: true, balance: Number(data.balance ?? 0), avatarUrl: BOOT.user.avatarUrl,
    docs: loadDocs(), scans: [], scansLoaded: false, credits: [], earn: null, billing: null,
    veil: { ...(data.veil || {}) },
  });
  renderSidebar(); applyLayout();
  loadCredits(); loadScans(); loadBilling(true);
  if (mode === 'login') {
    state.returning = true;
    const here = currentRoute();
    navigate(PUBLIC_ROUTES.includes(here) ? 'home' : here);
    toast('Logged in');
    return;
  }
  state.returning = false;
  navigate('home');
  toast(data.welcome_bonus_granted ? `Welcome! ${CONFIG.signupCredits} credits added` : `Welcome to ${CONFIG.brand}`);
}
signupDlg.addEventListener('close', () => {
  syncProto();
  if (signupOpener && document.contains(signupOpener) && !state.signedIn) signupOpener.focus();
});

function syncProto() {}

/* =========================================================
   Global actions (event delegation)
   ========================================================= */
function signUp() {
  openSignup({ intent: ALL_ITEMS.find(i => i.route === currentRoute())?.id });
}
async function signOut() {
  try { await API.logout(); } catch { /* the session is gone either way */ }
  BOOT.user = null; BOOT.plan = null; CONFIG.billing.plan = null; CONFIG.user.isAdmin = false;
  Object.assign(state, { signedIn: false, credits: [], docs: [], scans: [], scansLoaded: false, balance: 0, avatarUrl: null, earn: null, billing: null, assign: null, veil: {}, adm: null });
  clearTimeout(scanPollTimer);
  renderSidebar();
  applyLayout();
  navigate('landing');
}

document.addEventListener('click', (e) => {
  if (state.scanMenu && !e.target.closest('#scan-menu, [data-act="scan-menu"]')) closeScanMenu(false);
  if ($('#ed-menu') && !e.target.closest('#ed-menu, [data-act="ed-export"], [data-act="ed-versions"], [data-act="ed-open"], [data-act="sl-download"]')) edCloseMenu();
  if (!e.target.closest('.dl-wrap')) $('.dl-wrap.is-open')?.classList.remove('is-open');
  if ($('#profile-menu') && !$('#profile-menu').hidden && !e.target.closest('.profile')) toggleProfileMenu(false);
  const el = e.target.closest('[data-act]');
  if (!el) return;
  const act = el.dataset.act, page = ALL_ITEMS.find(i => i.route === currentRoute())?.id;
  if (act.startsWith('adm-')) { e.preventDefault(); adminAction(act, el); return; }
  switch (act) {
    case 'collapse':
      e.preventDefault();
      state.collapsed = !state.collapsed; store.set('collapsed', state.collapsed);
      hideTip(); renderSidebar(); applyLayout(); (isCollapsed() ? $('.sidebar-head .logo') : $('.collapse-btn')).focus(); break;
    case 'close-drawer': setDrawer(false); break;
    case 'profile-menu': toggleProfileMenu(); break;
    case 'profile-item': {
      const item = CONFIG.user.menu[+el.dataset.index];
      toggleProfileMenu(false);
      if (item.act === 'signout') signOut();
      else if (item.act === 'account') go('settings');
      else if (item.act === 'billing') go('billing');
      else if (item.act === 'admin') go('admin');
      break;
    }
    case 'acc-avatar': $('#acc-avatar-file').click(); break;
    case 'acc-avatar-remove': state.avatarUrl = null; renderSidebar(); render(); $('[data-act="acc-avatar"]')?.focus(); break;
    case 'acc-toggle-pw': {
      const inp = $('#' + el.dataset.for), show = inp.type === 'password';
      inp.type = show ? 'text' : 'password';
      el.setAttribute('aria-pressed', String(show));
      el.setAttribute('aria-label', (show ? 'Hide' : 'Show') + ' password');
      break;
    }
    case 'pricing': go('pricing'); break;
    case 'earn-copy': case 'earn-ref': case 'earn-convert': case 'earn-withdraw': case 'withdraw-close': earnAction(act, el); break;
    case 'plan-pick': {
      const plan = CONFIG.pricing.plans.find(x => x.id === el.dataset.plan);
      if (!state.signedIn) openSignup({ title: `Sign up to get ${plan.name}` });
      else startCheckout({ plan: plan.id }, el);
      break;
    }
    case 'payg-buy': {
      const cr = state.paygCredits || CONFIG.pricing.payg.start;
      const { creditPackQuantity } = paygValues(cr);
      if (!state.signedIn) openSignup({ title: 'Sign up to buy credits' });
      else startCheckout({ credits: cr, quantity: creditPackQuantity }, el);
      break;
    }
    case 'hdr-credits':   // credit history lives on Home
      if (currentRoute() === 'home') $('#hc-h')?.focus(); else { go('home'); setTimeout(() => $('#hc-h')?.focus(), 60); }
      break;
    case 'open-tutorials': if (state.drawerOpen) setDrawer(false); openTutorials(); break;
    case 'intro-play': openTutorials(); pickTutorial(CONFIG.tutorials.items.findIndex(t => t.id === 'start')); break;
    case 'intro-hide': store.set(introKey(), true); render(); $('#qs-h')?.focus(); toast('Hidden. Find it anytime in Tutorials'); break;
    case 'tut-close': tutDlg.close(); break;
    case 'tut-pick': pickTutorial(+el.dataset.index); break;
    case 'tut-tour': {
      const name = el.dataset.tourName, route = CONFIG.tours[name].route;
      tutDlg.close();
      if (currentRoute() === route) startTour(name); else { state.pendingTour = name; go(route); }
      break;
    }
    case 'support':   // the Help page holds the contact form
      if (currentRoute() === 'help') $('#help-topic')?.focus(); else { go('help'); setTimeout(() => $('#help-topic')?.focus(), 60); }
      break;
    case 'signup': e.preventDefault(); openSignup({ intent: el.dataset.intent }); break;
    case 'open-login': e.preventDefault(); openSignup({ mode: 'login' }); break;
    case 'close-signup': signupDlg.close(); break;
    case 'scroll-to': {
      e.preventDefault();
      const t = $('#' + el.dataset.target);
      if (t) t.scrollIntoView({ behavior: 'smooth' });
      else { go('landing'); setTimeout(() => $('#' + el.dataset.target)?.scrollIntoView(), 60); }
      break;
    }
    case 'theme':
      applyTheme(state.theme === 'light' ? 'dark' : 'light');
      renderSidebar(); applyLayout();
      if (PUBLIC_ROUTES.includes(currentRoute())) render();
      $(`${PUBLIC_ROUTES.includes(currentRoute()) ? '.pub-nav' : '#app-header'} [data-act="theme"]`)?.focus();
      break;
    case 'delete-doc': askDelete(el.dataset.id, el); break;
    case 'qs-upload': case 'qs-remove-file': case 'qs-check': case 'qs-humanize':
    case 'history-all': case 'history-less': case 'topup': case 'credits-more': case 'continue':
      homeAction(act, el); break;
    case 'clear-filter':state.docFilter = 'all'; rerenderDocs(); break;
    case 'run': runTool(page); break;
    case 'clear-tool': clearTool(page); break;
    case 'copy': $('.dl-wrap')?.classList.remove('is-open'); copyResult(); break;
    case 'dl-toggle': { const w = el.closest('.dl-wrap'); el.setAttribute('aria-expanded', w.classList.toggle('is-open')); break; }
    case 'dl-as': downloadResult(page, el.dataset.value); break;
    case 'next': handOff(page); break;
    case 'assign-upload': $('#assign-file').click(); break;
    case 'assign-example': {
      const a = assignState(); a.text = CONFIG.assignment.examples[+el.dataset.i].text;
      rerenderAssign('#assign-msg'); window.scrollTo(0, 0); break;
    }
    case 'assign-remove-file': assignState().files.splice(+el.dataset.i, 1); rerenderAssign('#assign-msg'); break;
    case 'assign-confirm': assignConfirm(); break;
    case 'assign-refine': sendAssignMessage(el.textContent); break;
    case 'assign-download': assignDownload(el); break;
    case 'assign-new':
      if (assignBusy(assignState())) break;
      state.assign = Object.assign(newAssign(), { hydrated: true });
      store.set(assignKey(), null);
      rerenderAssign('#assign-msg'); window.scrollTo(0, 0);
      break;
    case 'assign-retry': assignRun(assignState()); break;
    case 'assign-retry-price': { const a = assignState(); if (a.briefSource && !assignBusy(a)) assignPrice(a, a.briefSource); break; }
    case 'assign-refund': assignRefund(); break;
    case 'assign-topup': homeAction('topup', el); break;
    case 'start-tour':
      {
        const byIntent = Object.keys(CONFIG.tours).find(k => CONFIG.tours[k].route === state.profile?.intent);
        const name = el.dataset.tourName || byIntent || 'scan', route = CONFIG.tours[name].route;
        if (name === 'scan' && state.detMode !== 'turnitin') { state.detMode = 'turnitin'; if (currentRoute() === route) rerenderScan(); }
        if (currentRoute() === route) startTour(name); else { state.pendingTour = name; go(route); }
      }
      break;
    case 'det-mode': case 'qd-clear': case 'qd-run':
    case 'qd-humanize': case 'qd-turnitin':
      detAction(act, el); break;
    case 'scan-upload': case 'scan-remove-file': case 'scan-run': case 'scan-show': case 'scan-menu':
    case 'scan-delete': case 'scan-retry': case 'scan-download': case 'scan-highlights': case 'scan-humanize':
      scanAction(act, el); break;
    case 'ed-tab': case 'ed-detect': case 'ed-flag': case 'ed-humanize-sel': case 'ed-humanize-all': case 'ed-accept':
    case 'ed-reject': case 'ed-accept-all': case 'ed-reject-all': case 'ed-zoom': case 'ed-export':
    case 'ed-export-as': case 'ed-versions': case 'ed-restore': case 'ed-open': case 'ed-open-file': case 'ed-new':
    case 'ed-cite-insert': case 'ed-cite-ref': case 'ed-cmt-add': case 'ed-cmt-del': case 'ed-cmt-find':
      edAction(act, el); break;
    case 'rv-upload-doc': case 'rv-upload-brief': case 'rv-remove-doc': case 'rv-remove-brief': case 'rv-run':
    case 'rv-use-reqs': case 'rv-fix-format': case 'rv-editor': case 'rv-ai': case 'rv-add-brief':
      rvAction(act, el); break;
    case 'fmt-recheck': case 'fmt-banner-close':
    case 'fmt-upload': case 'fmt-remove-file': case 'fmt-parse': case 'fmt-settings': case 'fmt-group': case 'fmt-reset-group':
    case 'fmt-reset-all': case 'fmt-page': case 'fmt-run': case 'fmt-download': case 'fmt-another': case 'fmt-preview-open':
    case 'fmt-preview-close': case 'fmt-preset-form': case 'fmt-preset-cancel': case 'fmt-preset-save':
      fmtAction(act, el); break;
    case 'sl-upload': case 'sl-remove-file': case 'sl-jump-designs': case 'sl-generate': case 'sl-go': case 'sl-pick':
    case 'sl-filter': case 'sl-design': case 'sl-download': case 'sl-new':
      slAction(act, el); break;
    case 'veil-unlock': case 'veil-confirm': case 'veil-dlg-close': case 'veil-download': case 'veil-steps': case 'veil-scroll': case 'veil-copy': case 'veil-email':
      e.preventDefault(); veilAction(act, el); break;
  }
});

document.addEventListener('click', (e) => {
});

$('#menu-btn').addEventListener('click', () => setDrawer(true));
$('#backdrop').addEventListener('click', () => setDrawer(false));

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (!tip.hidden || tipTarget) { hideTip(); return; }
  if (formatState?.previewOpen && currentRoute() === 'format') { fmtSetPreviewOpen(false); return; }
  if (state.scanMenu) { closeScanMenu(true); return; }
  if (edCloseMenu(true)) return;
  if (!selPop.hidden) { hideSelPop(); return; }
  if (state.drawerOpen) setDrawer(false);
});

mobileMQ.addEventListener('change', () => { state.drawerOpen = false; renderSidebar(); applyLayout(); });

document.addEventListener('keydown', (e) => {
  const menu = $('#profile-menu');
  if (!menu || menu.hidden || !menu.contains(document.activeElement) && e.key !== 'Escape') return;
  const items = $$('[role="menuitem"]', menu), i = items.indexOf(document.activeElement);
  if (e.key === 'Escape') { toggleProfileMenu(false); $('.profile-btn').focus(); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  else if (e.key === 'Tab') toggleProfileMenu(false);
});

/* =========================================================
   Init
   ========================================================= */
applyTheme(store.get('theme', 'dark'));
$('#menu-btn').innerHTML = icon('menu');
const supportBtn = $('#support-btn');
supportBtn.innerHTML = icon('help');
supportBtn.setAttribute('aria-label', CONFIG.support.label);
supportBtn.dataset.tipTitle = CONFIG.support.label;
supportBtn.dataset.tipDesc = CONFIG.support.description;
supportBtn.dataset.act = 'support';
$('#topbar-logo').innerHTML = `<span class="logo-mark">${LOGO_SVG}</span><span>${esc(CONFIG.brand)}</span>`;
renderSidebar();
applyLayout();
window.addEventListener('hashchange', render);
// App header auto-hide: hide after scrolling down past the top, show again on any scroll up
(function bindHeaderAutoHide() {
  let lastY = scrollY;
  addEventListener('scroll', () => {
    const y = scrollY, root = document.documentElement;
    if (y < 120) { root.classList.remove('hdr-hidden'); lastY = y; return; }
    if (Math.abs(y - lastY) < 6) return;
    root.classList.toggle('hdr-hidden', y > lastY);
    lastY = y;
  }, { passive: true });
})();
if (!location.hash) history.replaceState(null, '', '#/' + (state.signedIn ? CONFIG.defaultRoute : 'landing'));
render();
loadCredits();
loadScans();
watchPaymentReturn();
