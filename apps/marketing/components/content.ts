export const publicSiteUrl = "https://fleetaisystems.com";

export const publicRoutes = [
  "/",
  "/features",
  "/how-it-works",
  "/solutions",
  "/pricing",
  "/contact",
] as const;
export const primaryNavigation = [
  { href: "/", label: "Home" },
  { href: "/features", label: "Features" },
  { href: "/solutions", label: "Solutions" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/contact", label: "Contact" },
] as const;

export const workflowSteps = [
  {
    number: "01",
    title: "Structure the operation",
    description: "Add active sites, owned and rented assets, and the people responsible for the work.",
    icon: "site",
  },
  {
    number: "02",
    title: "Deploy with context",
    description: "Place each asset at a site and create an effective-dated Driver or Operator assignment.",
    icon: "deploy",
  },
  {
    number: "03",
    title: "Capture work in the field",
    description: "Drivers record duty, trips, diesel, emergencies, and meter evidence—even with weak connectivity.",
    icon: "mobile",
  },
  {
    number: "04",
    title: "Review what happened",
    description: "Supervisors verify field events and resolve operational exceptions with a clear audit trail.",
    icon: "review",
  },
  {
    number: "05",
    title: "Run the next day better",
    description: "Owners use reports, maintenance readiness, and daily closure to keep the fleet moving.",
    icon: "insight",
  },
] as const;

export const assetTypes = [
  "Tippers",
  "Excavators",
  "Backhoe loaders",
  "Rollers",
  "Graders",
  "Owned + rented fleets",
] as const;

export const availableFeatures = {
  owner: [
    "Site and asset management",
    "Driver, Operator, and Supervisor access",
    "Deployments and effective-dated assignments",
    "Operational reporting and workbook exports",
    "Maintenance planning, proof, and history",
  ],
  driver: [
    "Start and end duty with dashboard evidence",
    "Trip completion and diesel entries",
    "Emergency reporting",
    "KM and HMR capture by asset capability",
    "Offline-first queue with safe retry",
  ],
  supervisor: [
    "Site-scoped operational visibility",
    "Trip, diesel, and meter review",
    "Emergency acknowledgement",
    "Maintenance proof review",
    "Daily completeness and closure workflow",
  ],
  intelligence: [
    "Assignment and deployment history",
    "Owned versus rented asset tracking",
    "Role-based controls and tenant isolation",
    "Evidence-backed audit history",
    "Site- and asset-level reporting",
  ],
} as const;
