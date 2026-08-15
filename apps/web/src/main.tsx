import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import KaApp from "./KaApp";
import "./styles.css";

const path = window.location.pathname.replace(/\/+$/, "") || "/";
const Root = path === "/ka" ? KaApp : App;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
