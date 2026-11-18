import ApiSession from './ApiSession.jsx'
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./ApiAdmin.jsx";
import "./style.css";
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ApiSession><App /></ApiSession>
  </React.StrictMode>,
);
