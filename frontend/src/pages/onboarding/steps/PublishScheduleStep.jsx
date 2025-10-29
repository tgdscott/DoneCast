import React from "react";
import { Label } from "@/components/ui/label";
import { formatInTimezone } from "@/lib/timezone";

export default function PublishScheduleStep({ wizard }) {
  const {
    freqUnit,
    selectedWeekdays,
    setSelectedWeekdays,
    notSureSchedule,
    setNotSureSchedule,
    selectedDates,
    setSelectedDates,
    resolvedTimezone,
  } = wizard;

  if (freqUnit === "week") {
    const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
    const toggleDay = (day) => {
      setSelectedWeekdays((previous) =>
        previous.includes(day)
          ? previous.filter((entry) => entry !== day)
          : [...previous, day]
      );
    };
    return (
      <div className="space-y-2">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {WEEKDAYS.map((day) => (
            <button
              type="button"
              key={day}
              onClick={() => toggleDay(day)}
              className={`border rounded p-2 text-center ${
                selectedWeekdays.includes(day)
                  ? "border-blue-600 ring-1 ring-blue-400"
                  : "hover:border-gray-400"
              }`}
            >
              {day}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 mt-2">
          <input
            id="notSureSchedule"
            type="checkbox"
            checked={notSureSchedule}
            onChange={(event) => setNotSureSchedule(event.target.checked)}
          />
          <Label htmlFor="notSureSchedule">I'm not sure yet</Label>
        </div>
      </div>
    );
  }

  const today = (() => {
    const t = new Date();
    return new Date(t.getFullYear(), t.getMonth(), t.getDate());
  })();
  const startOfThisMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const startOfNextMonth = new Date(today.getFullYear(), today.getMonth() + 1, 1);
  const endOfThisMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);
  const nextMonthWeekStart = (() => {
    const d = new Date(startOfNextMonth);
    const dow = d.getDay();
    const start = new Date(d);
    start.setDate(d.getDate() - dow);
    return start;
  })();
  const nextMonthWeekEnd = new Date(
    nextMonthWeekStart.getFullYear(),
    nextMonthWeekStart.getMonth(),
    nextMonthWeekStart.getDate() + 6
  );

  const remainingThisMonthDates = (() => {
    const arr = [];
    for (let day = today.getDate(); day <= endOfThisMonth.getDate(); day += 1) {
      arr.push(new Date(today.getFullYear(), today.getMonth(), day));
    }
    return arr;
  })();
  const dropCurrentMonth =
    remainingThisMonthDates.length > 0 &&
    remainingThisMonthDates.every(
      (date) => date >= nextMonthWeekStart && date <= nextMonthWeekEnd
    );
  const months = dropCurrentMonth ? [startOfNextMonth] : [startOfThisMonth, startOfNextMonth];

  const daysInMonth = (y, m) => new Date(y, m + 1, 0).getDate();
  const pad = (n) => String(n).padStart(2, "0");
  const toISO = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const toggleDate = (iso) => {
    setSelectedDates((previous) =>
      previous.includes(iso)
        ? previous.filter((entry) => entry !== iso)
        : [...previous, iso]
    );
  };
  const HEADERS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  return (
    <div className="space-y-4">
      {months.map((monthDate, index) => {
        const year = monthDate.getFullYear();
        const month = monthDate.getMonth();
        const isNextMonth =
          month === startOfNextMonth.getMonth() && year === startOfNextMonth.getFullYear();
        const totalDays = daysInMonth(year, month);
        const first = new Date(year, month, 1);
        const jsFirst = first.getDay();
        const cells = [];

        if (isNextMonth && dropCurrentMonth) {
          for (let i = 0; i < jsFirst; i += 1) {
            const prevDate = new Date(year, month, 1 - (jsFirst - i));
            if (prevDate >= today && prevDate >= nextMonthWeekStart && prevDate <= nextMonthWeekEnd) {
              const iso = toISO(prevDate);
              cells.push({ key: iso, iso, day: prevDate.getDate(), carry: true });
            } else {
              cells.push({ key: `b-${i}`, blank: true });
            }
          }
        } else {
          for (let i = 0; i < jsFirst; i += 1) {
            cells.push({ key: `b-${i}`, blank: true });
          }
        }

        for (let d = 1; d <= totalDays; d += 1) {
          const dateObj = new Date(year, month, d);
          const isThisMonth = month === today.getMonth() && year === today.getFullYear();
          if (isThisMonth && dateObj < today) {
            cells.push({ key: `p-${d}`, blank: true });
            continue;
          }
          const iso = toISO(dateObj);
          cells.push({ key: iso, iso, day: d });
        }

        while (cells.length % 7 !== 0) {
          cells.push({ key: `t-${cells.length}`, blank: true });
        }

        return (
          <div key={index} className="space-y-2">
            <div className="font-medium text-sm">
              {formatInTimezone(monthDate, { month: "long", year: "numeric" }, resolvedTimezone)}
            </div>
            <div className="grid grid-cols-7 gap-1 text-[11px] text-muted-foreground">
              {HEADERS.map((header) => (
                <div key={header} className="py-1 text-center">
                  {header}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {cells.map((cell) => {
                if (cell.blank) {
                  return <div key={cell.key} className="p-2" />;
                }
                const active = selectedDates.includes(cell.iso);
                return (
                  <button
                    type="button"
                    key={cell.key}
                    onClick={() => toggleDate(cell.iso)}
                    className={`border rounded p-2 text-center text-xs ${
                      active
                        ? "border-blue-600 ring-1 ring-blue-400"
                        : "hover:border-gray-400"
                    }`}
                  >
                    {cell.day}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-2 mt-2">
        <input
          id="notSureSchedule2"
          type="checkbox"
          checked={notSureSchedule}
          onChange={(event) => setNotSureSchedule(event.target.checked)}
        />
        <Label htmlFor="notSureSchedule2">I'm not sure yet</Label>
      </div>
    </div>
  );
}
