import { MapProvider } from "./context/MapContext";
import { SelectionProvider } from "./context/SelectionContext";
import { ExportProvider } from "./context/ExportContext";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";

function App() {
  return (
    <ErrorBoundary>
      <MapProvider>
        <SelectionProvider>
          <ExportProvider>
            <Layout />
          </ExportProvider>
        </SelectionProvider>
      </MapProvider>
    </ErrorBoundary>
  );
}

export default App;
