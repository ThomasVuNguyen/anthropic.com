import styles from "./page.module.css";
import Link from "next/link";

const highlights = [
  {
    title: "Project Vend: Phase two",
    category: "Policy",
    date: "Dec 18, 2025",
    href: "/www.anthropic.com/research/project-vend-2",
  },
  {
    title: "Building a C compiler with a team of parallel Claudes",
    category: "Engineering",
    date: "Feb 05, 2026",
    href: "/www.anthropic.com/engineering/building-c-compiler",
  },
  {
    title: "Preparing for AI’s economic impact",
    category: "Economic Futures",
    date: "Nov 20, 2025",
    href: "/www.anthropic.com/economic-futures",
  },
];

export default function Home() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.logo}>
          Anthropic
        </Link>
        <nav className={styles.nav}>
          <Link href="/research">Research</Link>
          <Link href="/economic-futures">Economic Futures</Link>
          <Link href="/news">News</Link>
          <a href="https://claude.ai/" target="_blank" rel="noopener noreferrer">
            Try Claude
          </a>
        </nav>
      </header>

      <main className={styles.main}>
        <section className={styles.hero}>
          <p className={styles.kicker}>V2 Rewrite In Progress</p>
          <h1 className={styles.title}>
            AI systems that can reason, collaborate, and build.
          </h1>
          <p className={styles.subtitle}>
            This is the first Next.js rewrite pass based on the scraped
            reference. Layout, typography, and interaction fidelity will be
            iterated section by section.
          </p>
          <div className={styles.actions}>
            <Link href="/research" className={styles.primary}>
              Explore research
            </Link>
            <a href="/reference/www.anthropic.com/index.html" className={styles.secondary}>
              Open scraped reference
            </a>
          </div>
        </section>

        <section className={styles.highlightGrid}>
          {highlights.map((item) => (
            <Link key={item.title} href={item.href} className={styles.card}>
              <p className={styles.cardMeta}>
                {item.category} · {item.date}
              </p>
              <h2 className={styles.cardTitle}>{item.title}</h2>
            </Link>
          ))}
        </section>
      </main>

      <footer className={styles.footer}>
        <p>Anthropic V2 rewrite workspace.</p>
        <p>Reference snapshot: `v2/reference/www.anthropic.com`</p>
      </footer>
    </div>
  );
}
