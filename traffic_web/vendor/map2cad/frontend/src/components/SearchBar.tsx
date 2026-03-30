import { useState, useRef, useEffect, useCallback } from "react";
import { searchLocation, type GeocodingResult } from "../services/geocoding";
import { useMapContext } from "../context/MapContext";
import { isGoogleMapsUrl, isShortLink, parseGoogleMapsUrl } from "../utils/parseGoogleMapsUrl";
import Spinner from "./ui/Spinner";

export default function SearchBar() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodingResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [noResults, setNoResults] = useState(false);
  const [urlError, setUrlError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null);
  const { flyTo } = useMapContext();

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setNoResults(false);
      return;
    }
    setLoading(true);
    setNoResults(false);
    try {
      const res = await searchLocation(q);
      setResults(res);
      setNoResults(res.length === 0);
      setShowResults(true);
    } catch {
      setResults([]);
      setNoResults(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!query.trim()) {
      setResults([]);
      setShowResults(false);
      setNoResults(false);
      return;
    }
    if (isGoogleMapsUrl(query)) return;
    timerRef.current = setTimeout(() => doSearch(query), 300);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [query, doSearch]);

  function handleSelect(result: GeocodingResult) {
    flyTo([result.lat, result.lng], 16);
    setQuery(result.displayName.split(",")[0]);
    setShowResults(false);
  }

  function handleChange(value: string) {
    setQuery(value);
    setUrlError(null);

    if (isGoogleMapsUrl(value)) {
      if (isShortLink(value)) {
        setUrlError("Short links not supported. Use the full URL from your browser address bar.");
        return;
      }
      const parsed = parseGoogleMapsUrl(value);
      if (parsed) {
        flyTo([parsed.lat, parsed.lng], parsed.zoom ?? 16);
        setQuery(`${parsed.lat.toFixed(4)}, ${parsed.lng.toFixed(4)}`);
        setResults([]);
        setShowResults(false);
      } else {
        setUrlError("Could not parse coordinates from this link.");
      }
    }
  }

  return (
    <div className="relative">
      <div className="relative">
        <input
          type="text"
          placeholder="Search or paste Google Maps link..."
          aria-label="Search for a location or paste a Google Maps link"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onFocus={() => results.length > 0 && setShowResults(true)}
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
        />
        {loading && (
          <div className="absolute right-2 top-1/2 -translate-y-1/2">
            <Spinner size="sm" />
          </div>
        )}
      </div>

      {urlError && (
        <p className="mt-1 text-xs text-red-500">{urlError}</p>
      )}

      {showResults && (results.length > 0 || noResults) && (
        <ul role="listbox" aria-label="Search results" className="absolute z-50 mt-1 max-h-60 w-full overflow-y-auto rounded border border-gray-200 bg-white shadow-lg">
          {results.map((r, i) => (
            <li
              key={i}
              role="option"
              tabIndex={0}
              onClick={() => handleSelect(r)}
              onKeyDown={(e) => e.key === "Enter" && handleSelect(r)}
              className="cursor-pointer px-3 py-2 text-sm text-gray-700 hover:bg-blue-50 focus:bg-blue-50 focus:outline-none"
            >
              {r.displayName}
            </li>
          ))}
          {noResults && (
            <li className="px-3 py-2 text-sm text-gray-400">No results found</li>
          )}
        </ul>
      )}
    </div>
  );
}
