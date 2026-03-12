import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Search from "./Search";
import PalestraDetail from "./PalestraDetail";
import "./App.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Search />} />
        <Route path="/palestras/:slug" element={<PalestraDetail />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
