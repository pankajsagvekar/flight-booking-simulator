import { useMemo, useState } from "react";

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function SearchFlights({ onSearch, loading }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [date, setDate] = useState(todayISO());

  const ready = useMemo(() => from && to && date, [from, to, date]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!ready) return;
    onSearch(from.toUpperCase(), to.toUpperCase(), date);
  };

  return (
    <form className="search-form" onSubmit={handleSubmit}>
      <div>
        <label>From (ICAO)</label>
        <input
          type="text"
          value={from}
          placeholder="e.g. VIDP"
          onChange={(e) => setFrom(e.target.value)}
          maxLength={4}
          required
        />
      </div>
      <div>
        <label>To (ICAO)</label>
        <input
          type="text"
          value={to}
          placeholder="e.g. VABB"
          onChange={(e) => setTo(e.target.value)}
          maxLength={4}
          required
        />
      </div>
      <div>
        <label>Departure date</label>
        <input
          type="date"
          value={date}
          min={todayISO()}
          onChange={(e) => setDate(e.target.value)}
          required
        />
      </div>
      <button type="submit" disabled={!ready || loading}>
        {loading ? "Searching..." : "Search flights"}
      </button>
    </form>
  );
}
