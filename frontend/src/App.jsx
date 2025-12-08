import { useEffect, useMemo, useState } from "react";
import "./App.css";
import api from "./api";
import SearchFlights from "./components/SearchFlights";

const STEP_LABELS = ["Select flight & seats", "Passenger info", "Payment"];
const initialContact = { name: "", email: "", phone: "" };
const emptyPayment = { status: null, message: "", pnr: null, reference: null };

function App() {
  const [searchMeta, setSearchMeta] = useState(null);
  const [flights, setFlights] = useState([]);
  const [loadingFlights, setLoadingFlights] = useState(false);
  const [flightError, setFlightError] = useState("");

  const [selectedFlight, setSelectedFlight] = useState(null);
  const [seatMap, setSeatMap] = useState([]);
  const [seatLoading, setSeatLoading] = useState(false);
  const [selectedSeats, setSelectedSeats] = useState([]);

  const [step, setStep] = useState(1);
  const [contactInfo, setContactInfo] = useState(initialContact);
  const [passengers, setPassengers] = useState([]);
  const [holdResult, setHoldResult] = useState(null);
  const [holdLoading, setHoldLoading] = useState(false);
  const [paymentState, setPaymentState] = useState(emptyPayment);
  const [paymentLoading, setPaymentLoading] = useState(false);

  const [historyEmail, setHistoryEmail] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [historyEntries, setHistoryEntries] = useState([]);

  const seatsNeeded = selectedSeats.length;
  const asCurrency = (value) => Number(value || 0).toFixed(0);

  useEffect(() => {
    setPassengers((prev) => {
      const clone = [...prev];
      if (seatsNeeded > clone.length) {
        const additions = new Array(seatsNeeded - clone.length)
          .fill(null)
          .map(() => ({ full_name: "", age: "", gender: "" }));
        return [...clone, ...additions];
      }
      return clone.slice(0, seatsNeeded);
    });
  }, [seatsNeeded]);

  const resetFlow = () => {
    setSelectedSeats([]);
    setPassengers([]);
    setHoldResult(null);
    setPaymentState(emptyPayment);
    setStep(1);
  };

  const handleSearch = async (origin, destination, date) => {
    resetFlow();
    setFlights([]);
    setSelectedFlight(null);
    setSeatMap([]);
    setSearchMeta({ origin, destination, date });
    setLoadingFlights(true);
    setFlightError("");
    try {
      const { data } = await api.get("/api/flights/search", {
        params: { origin, destination, date },
      });
      setFlights(data.flights || []);
    } catch (error) {
      setFlightError(error.message);
    } finally {
      setLoadingFlights(false);
    }
  };

  const loadSeats = async (flight) => {
    setSeatLoading(true);
    try {
      const { data } = await api.get(`/api/flights/${flight.flight_id}/seats`);
      setSeatMap(data);
      setSelectedSeats([]);
    } catch (error) {
      setFlightError(error.message);
    } finally {
      setSeatLoading(false);
    }
  };

  const selectFlight = (flight) => {
    setSelectedFlight(flight);
    setStep(1);
    setHoldResult(null);
    setPaymentState(emptyPayment);
    loadSeats(flight);
  };

  const toggleSeat = (seat) => {
    if (seat.is_reserved) return;
    const already = selectedSeats.find(
      (s) => s.seat_number === seat.seat_number
    );
    if (already) {
      setSelectedSeats((prev) =>
        prev.filter((s) => s.seat_number !== seat.seat_number)
      );
    } else {
      setSelectedSeats((prev) => [...prev, seat]);
    }
  };

  const proceedToPassengers = () => {
    if (!selectedFlight || !selectedSeats.length) return;
    if (!contactInfo.email || !contactInfo.name) return;
    setStep(2);
  };

  const handlePassengerChange = (index, field, value) => {
    setPassengers((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const handleHoldBooking = async (e) => {
    e.preventDefault();
    if (!selectedFlight) return;
    setHoldLoading(true);
    setHoldResult(null);
    try {
      const payload = {
        flight_id: selectedFlight.flight_id,
        contact_name: contactInfo.name,
        contact_email: contactInfo.email,
        contact_phone: contactInfo.phone,
        passengers: passengers.map((p) => ({
          full_name: p.full_name,
          age: p.age ? Number(p.age) : undefined,
          gender: p.gender || undefined,
        })),
        seats: selectedSeats.map((seat) => ({
          seat_number: seat.seat_number,
          cabin_class: seat.cabin_class,
        })),
        currency: "INR",
        hold_minutes: 15,
      };
      const { data } = await api.post("/api/bookings/hold", payload);
      setHoldResult(data);
      setStep(3);
    } catch (error) {
      setHoldResult({
        status: "ERROR",
        total_amount: 0,
        currency: "INR",
        hold_expires_at: null,
        price_breakdown: [],
        error: error.message,
      });
    } finally {
      setHoldLoading(false);
    }
  };

  const handlePayment = async (forcedOutcome) => {
    if (!holdResult?.booking_id) return;
    setPaymentLoading(true);
    setPaymentState({ status: "PROCESSING", message: "Processing payment..." });
    try {
      const { data } = await api.post(
        `/api/bookings/${holdResult.booking_id}/payment`,
        {
          payment_method: "card",
          force_outcome: forcedOutcome || null,
        }
      );
      setPaymentState({
        status: data.status,
        message: data.message,
        pnr: data.pnr,
        reference: data.payment_reference,
      });
    } catch (error) {
      setPaymentState({ status: "FAILED", message: error.message });
    } finally {
      setPaymentLoading(false);
    }
  };

  const handleCancelBooking = async () => {
    if (!holdResult?.booking_id) return;
    try {
      await api.post(`/api/bookings/${holdResult.booking_id}/cancel`);
      setPaymentState((prev) => ({
        ...prev,
        status: "CANCELLED",
        message: "Booking cancelled",
      }));
      loadSeats(selectedFlight);
    } catch (error) {
      setPaymentState({ status: "FAILED", message: error.message });
    }
  };

  const seatByCabin = useMemo(() => {
    return seatMap.reduce((acc, seat) => {
      acc[seat.cabin_class] = acc[seat.cabin_class] || [];
      acc[seat.cabin_class].push(seat);
      return acc;
    }, {});
  }, [seatMap]);

  const fetchHistory = async () => {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const params = historyEmail ? { email: historyEmail } : {};
      const { data } = await api.get("/api/bookings", { params });
      setHistoryEntries(data.bookings || []);
    } catch (error) {
      setHistoryError(error.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <header>
        <div>
          <p className="eyebrow">Flight Booking</p>
          <h1>Dynamic pricing & booking workflow</h1>
        </div>
        {searchMeta && (
          <div className="search-context">
            <strong>
              {searchMeta.origin} → {searchMeta.destination}
            </strong>
            <span>{searchMeta.date}</span>
          </div>
        )}
      </header>

      <section className="card">
        <h2>Find flights</h2>
        <SearchFlights onSearch={handleSearch} loading={loadingFlights} />
        {flightError && <p className="error">{flightError}</p>}
        {loadingFlights && <p>Loading flights...</p>}
        {!!flights.length && (
          <div className="flight-grid">
            {flights.map((flight) => (
              <article
                key={flight.flight_id}
                className={`flight-card ${
                  selectedFlight?.flight_id === flight.flight_id
                    ? "active"
                    : ""
                }`}
                onClick={() => selectFlight(flight)}
              >
                <div>
                  <p className="flight-number">
                    {flight.flight_number} • {flight.airline || "Unknown"}
                  </p>
                  <p>
                    {flight.departure_time || "??"} →{" "}
                    {flight.arrival_time || "??"}
                  </p>
                  <p className="flight-meta">
                    Seats: {flight.seats_left}/{flight.seats_total} • Demand:{" "}
                    {flight.demand_score}
                  </p>
                </div>
                <div className="flight-price">₹ {flight.price.toFixed(0)}</div>
              </article>
            ))}
          </div>
        )}
      </section>

      {selectedFlight && (
        <section className="card">
          <div className="step-header">
            {STEP_LABELS.map((label, index) => (
              <div
                key={label}
                className={`step ${index + 1 === step ? "current" : ""} ${
                  index + 1 < step ? "done" : ""
                }`}
              >
                <span>{index + 1}</span>
                <p>{label}</p>
              </div>
            ))}
          </div>

          {step === 1 && (
            <>
              <h2>Seat & traveler details</h2>
              <div className="contact-form">
                <div>
                  <label>Contact name</label>
                  <input
                    type="text"
                    value={contactInfo.name}
                    onChange={(e) =>
                      setContactInfo((prev) => ({
                        ...prev,
                        name: e.target.value,
                      }))
                    }
                    placeholder="Primary traveler"
                  />
                </div>
                <div>
                  <label>Email</label>
                  <input
                    type="email"
                    value={contactInfo.email}
                    onChange={(e) =>
                      setContactInfo((prev) => ({
                        ...prev,
                        email: e.target.value,
                      }))
                    }
                    placeholder="you@example.com"
                  />
                </div>
      <div>
                  <label>Phone (optional)</label>
                  <input
                    type="tel"
                    value={contactInfo.phone}
                    onChange={(e) =>
                      setContactInfo((prev) => ({
                        ...prev,
                        phone: e.target.value,
                      }))
                    }
                  />
                </div>
      </div>

              <div className="seat-groups">
                {seatLoading && <p>Loading seat map...</p>}
                {!seatLoading &&
                  Object.entries(seatByCabin).map(([cabin, seats]) => (
                    <div key={cabin} className="seat-group">
                      <header>
                        <h3>{cabin}</h3>
                        <span>{seats.length} seats</span>
                      </header>
                      <div className="seat-grid">
                        {seats.map((seat) => {
                          const taken = seat.is_reserved;
                          const isSelected = selectedSeats.some(
                            (s) => s.seat_number === seat.seat_number
                          );
                          return (
                            <button
                              key={seat.seat_number}
                              type="button"
                              className={`seat ${taken ? "taken" : ""} ${
                                isSelected ? "selected" : ""
                              }`}
                              onClick={() => toggleSeat(seat)}
                              disabled={taken}
                            >
                              <span>{seat.seat_number}</span>
                              <small>₹ {seat.price.toFixed(0)}</small>
        </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
              </div>

              <div className="step-actions">
                <div>
                  <p>
                    Selected seats: {selectedSeats.map((s) => s.seat_number).join(", ") || "None"}
        </p>
      </div>
                <button
                  type="button"
                  onClick={proceedToPassengers}
                  disabled={
                    !selectedSeats.length ||
                    !contactInfo.name ||
                    !contactInfo.email
                  }
                >
                  Continue to passengers
                </button>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <h2>Passenger manifest</h2>
              <form className="passenger-form" onSubmit={handleHoldBooking}>
                {passengers.map((passenger, index) => {
                  const seat =
                    selectedSeats[index] || {
                      seat_number: "TBD",
                      cabin_class: "",
                    };
                  return (
                    <div
                      key={`${seat.seat_number}-${index}`}
                      className="passenger-card"
                    >
                      <header>
                        Seat {seat.seat_number} • {seat.cabin_class || "N/A"}
                      </header>
                      <div className="grid">
                        <label>
                          Full name
                          <input
                            type="text"
                            value={passenger.full_name}
                            onChange={(e) =>
                              handlePassengerChange(
                                index,
                                "full_name",
                                e.target.value
                              )
                            }
                            required
                          />
                        </label>
                        <label>
                          Age
                          <input
                            type="number"
                            min="0"
                            value={passenger.age}
                            onChange={(e) =>
                              handlePassengerChange(index, "age", e.target.value)
                            }
                          />
                        </label>
                        <label>
                          Gender
                          <select
                            value={passenger.gender}
                            onChange={(e) =>
                              handlePassengerChange(
                                index,
                                "gender",
                                e.target.value
                              )
                            }
                          >
                            <option value="">Prefer not to say</option>
                            <option value="FEMALE">Female</option>
                            <option value="MALE">Male</option>
                            <option value="OTHER">Other</option>
                          </select>
                        </label>
                      </div>
                    </div>
                  );
                })}
                <div className="step-actions">
                  <button type="button" onClick={() => setStep(1)}>
                    Back
                  </button>
                  <button type="submit" disabled={holdLoading}>
                    {holdLoading ? "Placing hold..." : "Place hold"}
                  </button>
                </div>
              </form>
              {holdResult?.error && <p className="error">{holdResult.error}</p>}
            </>
          )}

          {step === 3 && holdResult && (
            <>
              <h2>Payment & confirmation</h2>
              <div className="hold-summary">
                <p>
                  Booking #{holdResult.booking_id} • Hold until{" "}
                  {holdResult.hold_expires_at
                    ? new Date(holdResult.hold_expires_at).toLocaleString()
                    : "n/a"}
                </p>
                <p>
                  Total due: ₹ {asCurrency(holdResult.total_amount)}{" "}
                  {holdResult.currency}
                </p>
              </div>
              <div className="payment-actions">
                <button
                  type="button"
                  onClick={() => handlePayment("SUCCESS")}
                  disabled={paymentLoading}
                >
                  Force success
                </button>
                <button
                  type="button"
                  onClick={() => handlePayment("FAIL")}
                  disabled={paymentLoading}
                >
                  Force failure
                </button>
                <button
                  type="button"
                  className="primary"
                  onClick={() => handlePayment()}
                  disabled={paymentLoading}
                >
                  Pay now
                </button>
                <button type="button" onClick={handleCancelBooking}>
                  Cancel booking
                </button>
              </div>
              {paymentState.status && (
                <div
                  className={`payment-status ${paymentState.status.toLowerCase()}`}
                >
                  <p>{paymentState.status}</p>
                  <p>{paymentState.message}</p>
                  {paymentState.pnr && (
                    <p>
                      PNR: <strong>{paymentState.pnr}</strong>
                    </p>
                  )}
                  {paymentState.reference && (
                    <p>Payment ref: {paymentState.reference}</p>
                  )}
                </div>
              )}
            </>
          )}
        </section>
      )}

      <section className="card">
        <h2>Booking history & cancellation</h2>
        <div className="history-form">
          <input
            type="email"
            placeholder="Filter by email (optional)"
            value={historyEmail}
            onChange={(e) => setHistoryEmail(e.target.value)}
          />
          <button type="button" onClick={fetchHistory} disabled={historyLoading}>
            {historyLoading ? "Fetching..." : "Fetch history"}
          </button>
        </div>
        {historyError && <p className="error">{historyError}</p>}
        <div className="history-list">
          {historyEntries.map((entry) => (
            <details key={entry.id}>
              <summary>
                #{entry.id} • {entry.flight_number} • {entry.status} • ₹{" "}
                {asCurrency(entry.total_amount)}
              </summary>
              <p>
                PNR: {entry.pnr || "Not assigned"} | Payment:{" "}
                {entry.payment_status}
              </p>
              <p>
                Route: {entry.origin} → {entry.destination} on {entry.date}
              </p>
              <p>
                Seats:{" "}
                {(entry.seats || [])
                  .map((seat) => seat.seat_number)
                  .join(", ") || "N/A"}
              </p>
              {(entry.passengers || []).length > 0 && (
                <ul>
                  {(entry.passengers || []).map((p) => (
                    <li key={`${entry.id}-${p.full_name}`}>
                      {p.full_name} {p.age ? `(${p.age})` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}

export default App;
