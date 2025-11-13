import { useState } from "react";

export default function SearchFlights({ onSearch }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (from && to) onSearch(from.toUpperCase(), to.toUpperCase());
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-white p-4 shadow-md rounded-md flex gap-4"
    >
      <input
        type="text"
        placeholder="From (e.g., DEL)"
        value={from}
        onChange={(e) => setFrom(e.target.value)}
        className="border p-2 rounded w-1/3"
      />
      <input
        type="text"
        placeholder="To (e.g., BOM)"
        value={to}
        onChange={(e) => setTo(e.target.value)}
        className="border p-2 rounded w-1/3"
      />
      <button
        type="submit"
        className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
      >
        Search
      </button>
    </form>
  );
}
