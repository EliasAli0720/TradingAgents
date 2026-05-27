// Standard page chrome: title (mirrors st.title in main pane) + subheader + caption.
export function PageTitle({ children }: { children: React.ReactNode }) {
  return <h1 className="st-title mb-4">{children}</h1>;
}

export function Subheader({ children }: { children: React.ReactNode }) {
  return <h2 className="st-sub">{children}</h2>;
}

export function Caption({ children }: { children: React.ReactNode }) {
  return <div className="st-caption mb-4">{children}</div>;
}

export function Info({ children }: { children: React.ReactNode }) {
  return (
    <div className="card text-sm border-l-4 border-info" style={{ borderLeftColor: '#2196F3' }}>
      {children}
    </div>
  );
}

export function Warning({ children }: { children: React.ReactNode }) {
  return (
    <div className="card text-sm" style={{ borderLeft: '4px solid #FFB300' }}>
      {children}
    </div>
  );
}

export function ErrorBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="card text-sm" style={{ borderLeft: '4px solid #F44336' }}>
      {children}
    </div>
  );
}
