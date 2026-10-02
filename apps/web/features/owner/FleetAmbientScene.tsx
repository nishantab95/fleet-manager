export function FleetAmbientScene() {
  return (
    <svg
      aria-hidden="true"
      className="owner-ambient"
      focusable="false"
      preserveAspectRatio="xMidYMid slice"
      viewBox="0 0 960 180"
    >
      <defs>
        <linearGradient id="owner-road-fade" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="currentColor" stopOpacity="0" />
          <stop offset="0.46" stopColor="currentColor" stopOpacity="0.22" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>

      <g className="owner-ambient__contours" fill="none" stroke="currentColor">
        <path d="M-34 42c84-36 165-34 244 8s164 43 256 4 185-35 279 10 178 43 267-2" />
        <path d="M-48 68c89-31 171-28 248 8s159 38 247 4 181-30 273 8 181 37 279 0" />
        <path d="M-60 98c92-25 176-21 252 10s155 32 239 3 176-24 267 8 184 32 285 2" />
      </g>

      <path className="owner-ambient__horizon" d="M0 132h126l34-16 45 5 33-24 59 35h150l32-13 37 6 45-35 52 42h347" fill="none" stroke="currentColor" />
      <path className="owner-ambient__road" d="M174 180 402 121h185l219 59Z" fill="url(#owner-road-fade)" />
      <path className="owner-ambient__road-line" d="m485 126-60 54M528 126l51 54" fill="none" stroke="currentColor" />

      <g className="owner-ambient__machine owner-ambient__machine--tipper" fill="none" stroke="currentColor">
        <path d="M698 116h57l14 16h31v18H678v-21h17Z" />
        <path d="m702 114 10-25h55l-12 27" />
        <path d="m710 91 44 19" />
        <circle cx="705" cy="151" r="8" />
        <circle cx="772" cy="151" r="8" />
      </g>

      <g className="owner-ambient__machine owner-ambient__machine--excavator" fill="none" stroke="currentColor">
        <path d="M82 147h82l12 7H72Z" />
        <path d="M103 145v-25h34l13 25" />
        <path d="m132 119 31-23 34 9" />
        <path d="m197 105 18 28-19 4" />
      </g>

      <g className="owner-ambient__route" fill="currentColor">
        <circle className="owner-ambient__motion owner-ambient__dot owner-ambient__dot--one" cx="414" cy="151" r="3.5" />
        <circle className="owner-ambient__motion owner-ambient__dot owner-ambient__dot--two" cx="474" cy="136" r="3" />
        <circle className="owner-ambient__motion owner-ambient__dot owner-ambient__dot--three" cx="542" cy="137" r="2.5" />
      </g>
    </svg>
  );
}
