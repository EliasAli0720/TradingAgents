export function WorkbenchPage() {
  return (
    <section className="page-stack">
      <h2>Analysis Workbench</h2>
      <form className="workbench-form">
        <label>
          Ticker
          <input defaultValue="SPY" />
        </label>
        <label>
          Analysis Date
          <input type="date" />
        </label>
        <label>
          Provider
          <select defaultValue="openai">
            <option value="openai">OpenAI</option>
            <option value="ollama">Ollama</option>
          </select>
        </label>
        <button type="button">Create Run</button>
      </form>
    </section>
  );
}
