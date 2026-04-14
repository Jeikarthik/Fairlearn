export default function SectionCard({ title, subtitle, actions, children, className = "" }) {
  return (
    <section className={`section-card ${className}`.trim()}>
      {(title || subtitle || actions) && (
        <div className="section-head">
          <div>
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p className="section-subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="section-actions">{actions}</div> : null}
        </div>
      )}
      {children}
    </section>
  );
}
