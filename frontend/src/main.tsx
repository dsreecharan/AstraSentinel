import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

const mountNode = document.getElementById("root");
if (!mountNode) {
  throw new Error("Dashboard root element is missing");
}

createRoot(mountNode).render(<App />);
