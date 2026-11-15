import React from "react";
import {tr} from "./locale.js";

export function LoadingStatus() {
  return <div className="loading-status" role="status">
    <span className="loading-spinner" aria-hidden="true" />
    <p>{tr("플레이 기록을 불러오는 중", "Loading replay data")}</p>
  </div>;
}
