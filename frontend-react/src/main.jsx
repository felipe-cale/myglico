import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "@fontsource-variable/fredoka/wght.css";
import "@fontsource-variable/figtree/wght.css";
import "./styles.css";
import "./brand.css";
import "./i18n";

const routerBasename = import.meta.env.BASE_URL === "/" ? "/" : import.meta.env.BASE_URL.replace(/\/$/, "");

ReactDOM.createRoot(document.getElementById("root")).render(
  <BrowserRouter basename={routerBasename}>
    <App />
  </BrowserRouter>
);
