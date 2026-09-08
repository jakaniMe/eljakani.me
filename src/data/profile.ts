/* ============================================================================
   SITE CONTENT, EDIT THIS FILE TO UPDATE THE WHOLE SITE.
   For normal content changes you should not need to touch any component.

   Search for "TODO(input)" to find every value waiting for you.

   PHOTOS: drop image files into  public/images/  and list their filenames in
   the `images: [...]` arrays below (e.g. images: ["devoxx25-1.jpg"]).
   - Leave an images array empty  []  to show NO gallery for that item.
   - If a listed file is missing, a tasteful "photo soon" tile shows instead
     of a broken image, so you can keep the data now and add photos later.
============================================================================ */

export const profile = {
  name: "Yassin El Jakani",
  displayName: "Dr. Yassin El Jakani",
  title: "Assistant Professor · Maître de Conférences",
  affiliation: "Faculty of Sciences, Université Ibn Zohr · LabSIV",
  location: "Agadir, Morocco",
  tagline:
    "I research at the intersection of artificial intelligence and the edge, building QoS-aware IoT and edge systems, and I teach what I learn.",

  // src/imgs/profile.jpg, a square-ish portrait (yours is 1110×1148, perfect)
  photoAlt: "Portrait of Dr. Yassin El Jakani",

  // public/cv.pdf, TODO(input): replace the placeholder PDF with your real CV
  cv: "/cv.pdf",

  // TODO(input): confirm this is the address you want published on the site.
  // (Alternative personal address: jakani.yassin@gmail.com)
  email: "y.eljakani@uiz.ac.ma",

  links: {
    // Social media: LinkedIn only for now, uncomment the others when ready.
    linkedin: "https://www.linkedin.com/in/yassin-el-jakani/",
    // github: "https://github.com/jakanime",                                    // TODO(later)
    // twitter: "https://x.com/YOUR_HANDLE",                                     // TODO(later)

    // Academic profiles (rendered as links in Publications when uncommented):
    // scholar: "https://scholar.google.com/citations?user=AismvOgAAAAJ&hl=fr",  // TODO(later)
    // researchgate: "https://www.researchgate.net/profile/Yassin-Eljakani",     // TODO(later)
    // orcid: "https://orcid.org/0009-0005-8188-2141",                           // TODO(later)
  } as Record<string, string>,
};

/* --- Hero availability badge + collaboration modal ------------------------- */
export const availability = {
  badge: "Open to collaboration • Research · Speaking.",
  lookingFor: "Research collaboration, consulting.",
  focus: "Deep learning and Edge AI for Quality of service optimization in IoT networks.",
  where: "Based in Agadir, Morocco, open to remote collaboration.",
  pitch:
    "I lecture and supervise; and doing research using deep-learning models onto tiny devices. If you are organising a conference, running a lab, or building something at the edge, let's talk.",
};

/* Short badges under the hero. */
export const highlights = [
  "PhD in AI & IoT",
  "Assistant Professor @ FS Agadir",
  "Edge AI & IoT",
  "Conference Speaker",
  "volunteering at Sciencespourtous.net",
];

/* --- Research areas --------------------------------------------------------- */
export type ResearchArea = { heading: string; body: string; icon: string };
export const research: ResearchArea[] = [
  {
    heading: "Edge, IoT & deep learning",
    body: "Designing compact deep-learning models for resource-constrained edge and IoT hardware.",
    icon: "lucide:cpu",
  },
  {
    heading: "Cross-layer QoS prediction",
    body: "Predicting and balancing conflicting quality-of-service metrics across IoT network stacks.",
    icon: "lucide:gauge",
  },
  {
    heading: "IoT & physical-layer security",
    body: "Improving physical-layer security in IoT using deep sequence models.",
    icon: "lucide:shield-check",
  },
  {
    heading: "Federated learning & IoT",
    body: "Edge intelligence, federated learning, and semantic communication for the device–edge–core hierarchy of IoT networks.",
    icon: "lucide:network",
  },
];

/* --- Positions (academic experience) ----------------------------------------
   `logo` is optional: add e.g. "/logos/uiz.png" (file in public/logos/) to show
   an institution logo; otherwise a themed icon tile is rendered.
---------------------------------------------------------------------------- */
export type Position = {
  org: string;
  url?: string;
  role: string;
  type: string;
  logo?: string;
  icon: string;
  location: string;
  period: string;
  highlights: { text: string; icon: string }[];
};

export const positions: Position[] = [
  {
    org: "Faculty of Sciences, Université Ibn Zohr",
    url: "https://fsa.uiz.ac.ma/", // TODO(input): verify institutional URL
    role: "Assistant Professor · Maître de Conférences",
    type: "Full-time",
    icon: "lucide:landmark",
    location: "Agadir, Morocco",
    period: "2025 - Present",
    highlights: [
      { text: "Teaching Python programming and C/C++ lab work at the Faculty of Sciences, and network management at ENSA Agadir", icon: "lucide:presentation" },
      { text: "Research at LabSIV on Edge AI, federated learning, and QoS-aware IoT systems", icon: "lucide:flask-conical" },
      { text: "Mentoring students and serving on graduation-project (PFE) juries", icon: "lucide:users-2" },
    ],
  },
  {
    org: "LabSIV, Université Ibn Zohr",
    url: "https://www.uiz.ac.ma/", // TODO(input): verify lab URL
    role: "Doctoral Researcher",
    type: "PhD",
    icon: "lucide:microscope",
    location: "Agadir, Morocco",
    period: "2021 - 2025",
    highlights: [
      { text: "Thesis on deep learning and cross-layer parametric analyses for QoS prediction and security in IoT networks, defended June 2025 with distinction « Very Honorable »", icon: "lucide:scroll-text" },
      { text: "First-author publications, including a Q1 journal paper in Elsevier's Ad Hoc Networks (~97% average R² across four QoS metrics)", icon: "lucide:file-badge" },
      { text: "Represented Morocco in Huawei ICT competitions and spoke at national developer conferences", icon: "lucide:megaphone" },
    ],
  },
];

/* --- Publications ------------------------------------------------------------
   Wrap YOUR name in **double asterisks** to bold it in the author list.
   links: type ∈ "doi" | "pdf" | "preprint" | "view". Omit links you don't have.
---------------------------------------------------------------------------- */
export type PubLink = { type: "doi" | "pdf" | "preprint" | "view"; href: string };
export type Publication = {
  venue: string;
  year: string;
  kind: string; // "Journal" | "Book chapter" | "Conference"
  title: string;
  authors: string;
  abstract: string;
  badges?: string[]; // e.g. ["Q1", "First author"]
  tags?: string[];
  links?: PubLink[];
};

export const publications: Publication[] = [
  {
    venue: "Ad Hoc Networks (Elsevier)",
    year: "2025",
    kind: "Journal",
    title:
      "Predicting diverse QoS metrics in IoT: An adaptive deep learning cross-layer approach for performance balancing",
    authors: "**Yassin El Jakani**, Abdellah Boulouz, Craig Thomson",
    abstract:
      "Wireless sensor networks present dynamic challenges that require carefully balancing conflicting Quality-of-Service metrics. This work introduces novel application-layer control parameters working with a dynamic multi-layer perceptron and an adaptable Weighted Error Squared loss to maintain an optimal trade-off between SNR, Maximum Goodput, Energy Consumption, and Packet Delivery Ratio on IEEE 802.15.4 networks, reaching ~97% average R² (97/99/98/93% for SNR/PDR/MGP/EC). To our knowledge, it is the first integrated approach of its kind in WSNs.",
    badges: ["Q1", "First author", "IF 4.4 · CiteScore 10.2"],
    tags: ["Deep Learning", "IoT QoS", "IEEE 802.15.4", "Bayesian Optimization"],
    links: [{ type: "doi", href: "https://doi.org/10.1016/j.adhoc.2025.103769" }],
  },
  {
    venue: "Springer, Advances in Machine Intelligence & CS Applications",
    year: "2023",
    kind: "Book chapter",
    title:
      "Physical Layer Parameters for Jamming Attack Detection in VANETs: A Long Short Term Memory Approach",
    authors: "**Yassin El Jakani**, Abdellah Boulouz, Said El Hachemy",
    abstract:
      "Availability is a leading security requirement for vehicular ad hoc networks (VANETs) underpinning intelligent transportation systems. This chapter proposes an LSTM-based approach that exploits physical-layer parameters to detect radio-frequency jamming / denial-of-service attacks against connected vehicles.",
    badges: ["First author"],
    tags: ["VANET", "Security", "LSTM", "Jamming Detection"],
    links: [{ type: "doi", href: "https://doi.org/10.1007/978-3-031-29313-9_27" }],
  },
  {
    venue: "Book chapter",
    year: "2023",
    kind: "Book chapter",
    title: "A Nearest Neighbor-Based Hamiltonian Clustering Algorithm",
    authors: "Said El Hachemy, Abdellah Boulouz, **Yassin El Jakani**",
    abstract:
      "Since most real-world data is unlabeled, robust unsupervised and semi-supervised clustering is essential. This chapter introduces a clustering algorithm built on a nearest-neighbor-based Hamiltonian path to draw conclusions out of unlabeled data.",
    tags: ["Clustering", "Unsupervised Learning"],
    links: [
      {
        type: "view",
        href: "https://www.researchgate.net/publication/375318319_A_Nearest_Neighbor-Based_Hamiltonian_Clustering_Algorithm",
      },
    ],
  },
  {
    venue: "Book chapter",
    year: "2023",
    kind: "Book chapter",
    title:
      "Energy-efficient Next Hop Selection for Topology Creation in Wireless Sensor Networks",
    authors: "Said El Hachemy, Abdellah Boulouz, **Yassin El Jakani**",
    abstract:
      "Topology creation is a key criterion for a better routing experience in wireless sensor networks, especially for applications that require long-term deployment with infrequent maintenance. This chapter proposes an energy-efficient next-hop selection scheme to extend network lifetime.",
    tags: ["WSN", "Energy Efficiency", "Routing"],
    links: [
      {
        type: "view",
        href: "https://www.researchgate.net/publication/369864171_Energy-efficient_Next_Hop_Selection_for_Topology_Creation_in_Wireless_Sensor_Networks",
      },
    ],
  },
  {
    venue: "ITM Web of Conferences (ICAIE'2022)",
    year: "2022",
    kind: "Conference",
    title:
      "Performances prediction in Wireless Sensor Networks: A survey on Deep learning based-approaches",
    authors:
      "**Yassin El Jakani**, Abdellah Boulouz, Mohamed Ben Salah, Said El Hachemy",
    abstract:
      "The dynamism and successive changes in node distribution are defining traits of wireless sensor networks, forcing designers to configure many parameters at each layer of the stack. This open-access survey reviews deep-learning-based approaches for predicting WSN performance across the physical, MAC, network, and application layers.",
    badges: ["Open access", "First author"],
    tags: ["WSN", "Deep Learning", "Survey"],
    links: [{ type: "doi", href: "https://doi.org/10.1051/itmconf/20224301010" }],
  },
];

/* --- Talks & conferences -----------------------------------------------------
   images: filenames inside public/images/, leave [] for talks with no photos.
---------------------------------------------------------------------------- */
export type Talk = {
  year: string;
  event: string;
  place: string;
  title: string;
  blurb?: string;
  images: string[];
  link?: string;
};

export const talks: Talk[] = [
  {
    year: "2025",
    event: "Devoxx Morocco 2025",
    place: "Marrakech · Nov 2025",
    title: "Edge AI, Federated Learning, and IoT: Perfect Match?",
    blurb:
      "Second time on the Devoxx stage, exploring the synergies between Edge AI, federated learning, and IoT at the edge.",
    images: ["devox20251.jfif", "devox20252.jfif", "devox20253.jfif"],
  },
  {
    year: "2024",
    event: "Devoxx Morocco 2024",
    place: "Palm Plaza, Marrakech · Oct 2024",
    title: "Risk Management: Elevate Your Defense with NIST Cybersecurity Framework 2.0",
    blurb: "A practical walkthrough of NIST CSF 2.0 for security and risk management.",
    images: ["devox20241.jfif", "devox20242.jfif", "devox20243.jfif"],
  },
  {
    year: "2024",
    event: "DevFest El Jadida 2024",
    place: "ENSA El Jadida",
    title: "Edge AI, Federated Learning, and IoT: Perfect Match?",
    blurb: "On interoperability in IoT and how Edge AI and federated learning fit together.",
    images: ["gdgjadida1.jfif", "gdgjadida2.jfif", "gdgjadida3.jfif"],
  },
  {
    year: "2023",
    event: "DevFest On Campus Souss-Massa",
    place: "Cité de l'Innovation, Agadir",
    title: "Introduction to LLMs & AI understanding",
    blurb: "Demystifying large language models for a mixed audience of students and developers.",
    images: ["gdgdagadir1.jfif", "gdgdagadir2.jfif"],
  },
  {
    year: "2021–2022",
    event: "GDSC Université Ibn Zohr",
    place: "ML Ready · 30 Days of ML",
    title: "ML foundations: Information Theory & Convolutional Neural Networks",
    blurb: "A series of community machine-learning sessions, several delivered in Darija.",
    images: ["ml1.jfif"],
  },
];

/* --- Prizes & recognition ---------------------------------------------------- */
export type Prize = {
  year: string;
  title: string;
  org: string;
  detail: string;
  images: string[];
};

export const prizes: Prize[] = [
  {
    year: "2025",
    title: "PhD, distinction « Very Honorable »",
    org: "Faculty of Sciences, Université Ibn Zohr",
    detail:
      "Thesis: “Deep learning and parametric analyses applied to the Internet of Things: a cross-layer approach for QoS prediction and security in IoT networks.” Defended 21 June 2025.",
    images: ["phd1.jfif", "phd3.jfif", "phd2.jfif", "phd4.jfif", "phd5.jfif"],
  },
  {
    year: "2022",
    title: "First runner-up, Huawei Developer Competition, Northern Africa",
    org: "Huawei · Cairo ICT",
    detail:
      "Among 110+ academic and industry teams; top 11 in Northern Africa. An AI + cloud solution for education in Morocco, built with Said El Hachemy.",
    images: ["tech1.jfif", "tech2.jfif", "tech3.jfif", "tech4.jfif"],
  },
  {
    year: "2022",
    title: "Huawei ICT Competition, Cloud Track, representing Morocco",
    org: "Huawei ICT Academy · Université Ibn Zohr",
    detail:
      "Represented FS Agadir / UIZ in the Northern Africa regional phase across cloud, big data, and AI; recognised at the Digitech Ecosystem Summit (Skhirat).",
    images: ["huawei1.jfif", "huawei2.jfif", "huawei3.jfif", "huawei4.jfif", "huawei5.jfif"],
  },
  {
    year: "2022",
    title: "Selected participant, Huawei Seeds for the Future (Morocco)",
    org: "Huawei",
    detail:
      "Among the country's elite ICT talents. Tech4Good team “Goal Diggers” built an AI + IoT + Cloud assistant supporting people living with dementia.",
    images: ["seeds2.jfif", "seeds1.jfif"],
  },
  {
    year: "2023",
    title: "Selected participant, MoroccoAI Summer School",
    org: "MoroccoAI × Al Akhawayn University",
    detail:
      "One of 50 selected from Morocco's AI community; hands-on work on LLMs for flipped learning (Transformers, NLP, TinyML, GNNs, federated learning).",
    images: ["ai1.jfif", "ai2.jfif"],
  },
];

/* --- Certifications ----------------------------------------------------------
   `url` is optional, add credential links when you have them.
---------------------------------------------------------------------------- */
export type Cert = { name: string; issuer: string; url?: string };
export const certifications: Cert[] = [
  { name: "TensorFlow Developer Certificate", issuer: "TensorFlow / Google" },
  { name: "Google Data Analytics Professional Certificate", issuer: "Google / Coursera" },
  { name: "Deep Learning Specialization", issuer: "DeepLearning.AI / Coursera" },
  { name: "HCIA-AI", issuer: "Huawei ICT Academy" },
  { name: "HCIA-Cloud Services", issuer: "Huawei ICT Academy" },
  { name: "HCIA Routing & Switching", issuer: "Huawei ICT Academy" },
  { name: "HCIA-5G", issuer: "Huawei ICT Academy" },
  { name: "Cloud Big Data & Machine Learning", issuer: "Google Cloud / Coursera" },
  { name: "Intro to IoT & Embedded Systems", issuer: "UC Irvine / Coursera" },
];

/* --- Teaching ---------------------------------------------------------------- */
export const teachingStatement =
  "My teaching connects fundamentals with practice, moving students from concepts to implementation through programming, hands-on labs, projects, and real examples from AI, IoT, cloud, and cybersecurity.";

export const teaching = [
  { course: "Programmation Python", where: "Faculty of Sciences, Agadir" },
  { course: "Gestion des réseaux", where: "ENSA, Agadir" },
  { course: "Travaux pratiques C / C++", where: "Faculty of Sciences, Agadir" },
];

export const teachingActivities = [
  "Student mentoring & graduation-project (PFE) juries at FS Agadir",
  "Oracle campus tour, PFE pipeline & certification guidance",
  "Huawei ICT Competition workshops & certification pathways",
];

/* --- Education ---------------------------------------------------------------
   `logo` optional, same as positions. Add earlier degrees when ready.
---------------------------------------------------------------------------- */
export type Degree = {
  school: string;
  schoolUrl?: string;
  logo?: string;
  location: string;
  period: string;
  degree: string;
  note?: string;
};

export const education: Degree[] = [
  {
    school: "Faculty of Sciences, Université Ibn Zohr",
    schoolUrl: "https://fsa.uiz.ac.ma/", // TODO(input): verify URL
    location: "Agadir, Morocco",
    period: "2021 - 2025",
    degree: "PhD in Computer Science, Deep learning & cross-layer analyses for QoS prediction and security in IoT networks",
    note: "Distinction « Very Honorable » · defended 21 June 2025",
  },
  // TODO(input): add your earlier degrees, e.g.:
  // {
  //   school: "Your university",
  //   schoolUrl: "https://...",
  //   location: "City, Country",
  //   period: "20XX - 20XX",
  //   degree: "Master's degree in ...",
  // },
];

/* --- Community & outreach ---------------------------------------------------- */
export type Community = {
  title: string;
  role: string;
  period?: string;
  body: string[];
  images: string[];
};

export const communityIntro =
  "Through Sciences Pour Tous, I help run volunteer-driven programs that bring coding, robotics, and scientific orientation to young learners.";

export const community: Community[] = [
  {
    title: "Youth Coding Days",
    role: "Mentor & organiser",
    body: [
      "Multiple editions across Souss-Massa (Aoulouz, Ouijane/Tiznit, CISM) teaching Python, C, Arduino and robotics to young learners, free, with certificates.",
    ],
    images: [],
  },
  {
    title: "Agadir Smart City Meeting (ASCM)",
    role: "Organiser & contributor",
    body: [
      "A volunteer-driven civic-tech platform on smart cities, IoT, and cybersecurity awareness, bringing experts and citizens together in Agadir.",
    ],
    images: [],
  },
  {
    title: "Caravane du Numérique",
    role: "Contributor",
    body: [
      "Coding workshops and educational orientation, democratising digital skills beyond major cities.",
    ],
    images: [],
  },
  {
    title: "Orientation Pour Tous",
    role: "Contributor",
    body: [
      "Guidance sessions helping young students navigate post-baccalaureate study and career paths in science and technology.",
    ],
    images: [],
  },
];

/* --- SEO / meta --------------------------------------------------------------- */
export const meta = {
  siteTitle: "Yassin El Jakani - Assistant Professor · Edge AI & IoT",
  description:
    "Dr. Yassin El Jakani, Assistant Professor at Université Ibn Zohr, Agadir. Research on Edge AI, lightweight deep learning, IoT & physical-layer security, and network QoS.",
  knowsAbout: [
    "Artificial Intelligence",
    "Edge Computing",
    "Internet of Things",
    "Deep Learning",
    "Federated Learning",
    "Network QoS",
    "Physical-layer Security",
  ],
};

/* --- Sticky navigation (order = reading order) --------------------------------
   Icons are keys resolved in StickyNavigation.tsx.
---------------------------------------------------------------------------- */
export const navItems = [
  { id: "research", label: "Research", icon: "FlaskConical" },
  { id: "positions", label: "Positions", icon: "BriefcaseBusiness" },
  { id: "publications", label: "Publications", icon: "BookOpen" },
  { id: "talks", label: "Talks", icon: "Mic" },
  { id: "awards", label: "Awards", icon: "Trophy" },
  { id: "teaching", label: "Teaching", icon: "GraduationCap" },
  { id: "community", label: "Community", icon: "Sprout" },
];
