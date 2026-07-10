import { useTranslation } from "react-i18next";

export default function Pagination({ page, pages, onPageChange }) {
  const { t } = useTranslation();
  const items = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, start + 4);

  for (let current = start; current <= end; current += 1) {
    items.push(
      <button
        key={current}
        type="button"
        className={`react-pagination__item${current === page ? " is-active" : ""}`}
        onClick={() => onPageChange(current)}
      >
        {current}
      </button>
    );
  }

  return (
    <div className="react-pagination">
      <button type="button" className="react-pagination__edge" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>
        {t("pagination.previous")}
      </button>
      <div className="react-pagination__list">{items}</div>
      <button type="button" className="react-pagination__edge" onClick={() => onPageChange(page + 1)} disabled={page >= pages}>
        {t("pagination.next")}
      </button>
    </div>
  );
}
