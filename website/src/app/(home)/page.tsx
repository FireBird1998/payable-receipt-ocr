import Link from 'next/link';
import { appName, docsRoute, repoUrl } from '@/lib/shared';

export default function HomePage() {
  return (
    <main className="landing-root flex flex-1">
      <section className="landing-shell mx-auto flex w-full max-w-6xl flex-col gap-10 px-6 py-12 md:py-16">
        <div className="grid items-start gap-10 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="space-y-7">
            <p className="landing-tag">Alpha documentation for local payable OCR</p>
            <h1 className="landing-title">
              Safe-by-default receipt OCR for INR delivery bills.
            </h1>
            <p className="landing-lead">
              <strong>{appName}</strong> helps Python integrators and contributors parse Blinkit,
              Swiggy, and Zepto payable receipts completely offline. It adapts between 4 and 12
              Tesseract passes, then always requires human confirmation before any result can be
              accepted.
            </p>
            <div className="landing-cta-row">
              <Link className="landing-cta-primary" href={docsRoute}>
                Read the docs
              </Link>
              <Link className="landing-cta-secondary" href={repoUrl}>
                View on GitHub
              </Link>
            </div>
            <ul className="landing-facts" role="list">
              <li>Local/offline execution; no hosted HTTP service is provided.</li>
              <li>INR scope today: Blinkit, Swiggy, and Zepto receipt formats.</li>
              <li>Project status: alpha; behavior and templates may evolve quickly.</li>
            </ul>
          </div>

          <article className="receipt-slip" aria-label="Recognition safety contract">
            <header className="receipt-slip-head">
              <p className="receipt-kicker">recognition slip</p>
              <p className="receipt-status">pending human confirmation</p>
            </header>
            <dl className="receipt-grid">
              <div>
                <dt>total detected</dt>
                <dd>₹289.86</dd>
              </div>
              <div>
                <dt>evidence</dt>
                <dd>review</dd>
              </div>
              <div>
                <dt>confirmation</dt>
                <dd>required</dd>
              </div>
              <div>
                <dt>persistence</dt>
                <dd>not authorized</dd>
              </div>
            </dl>
            <p className="receipt-footnote">
              Output is only a suggestion. Operators must verify and approve before using any
              extracted value.
            </p>
          </article>
        </div>
      </section>
    </main>
  );
}
