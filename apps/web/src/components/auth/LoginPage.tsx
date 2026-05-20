import { FormEvent, useState } from "react";

type LoginPageProps = {
  onLogin: (token: string) => void;
};

export function LoginPage({ onLogin }: LoginPageProps) {
  const [token, setToken] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (token.trim()) {
      onLogin(token.trim());
    }
  }

  return (
    <main className="login-page">
      <form onSubmit={submit} className="login-form">
        <h1>TradingAgents</h1>
        <label>
          Access Token
          <input value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
        <button type="submit">Login</button>
      </form>
    </main>
  );
}
