import { Component } from "react";
import ErrorPage from "../pages/ErrorPage";

// A crash while rendering a page shows the friendly error screen instead of a blank page.
export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    // Kept for the browser console; nothing is sent anywhere.
    console.error(error);
  }

  render() {
    return this.state.failed ? <ErrorPage /> : this.props.children;
  }
}
