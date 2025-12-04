import React from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

export default function PublishPlanStep({ wizard }) {
  const {
    freqUnit,
    setFreqUnit,
    freqCount,
    setFreqCount,
    cadenceError,
    setCadenceError,
    selectedWeekdays,
    setSelectedWeekdays,
    selectedDates,
    setSelectedDates,
    notSureSchedule,
    setNotSureSchedule,
  } = wizard;

  const toggleWeekday = (day) => {
    const next = selectedWeekdays.includes(day)
      ? selectedWeekdays.filter((d) => d !== day)
      : [...selectedWeekdays, day];
    setSelectedWeekdays(next);
  };

  const toggleDate = (date) => {
    const next = selectedDates.includes(date)
      ? selectedDates.filter((d) => d !== date)
      : [...selectedDates, date];
    setSelectedDates(next);
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">Publishing Plan</h2>
        <p className="text-sm text-muted-foreground">
          Choose your publishing frequency and preferred days/dates. You can change this later in Settings.
        </p>
      </div>

      <div className="space-y-3">
        <Label className="text-base">Frequency</Label>
        <div className="flex items-center gap-3">
          <select
            className="border rounded px-3 py-2"
            value={freqUnit}
            onChange={(e) => setFreqUnit(e.target.value)}
          >
            <option value="week">Weekly</option>
            <option value="bi-weekly">Bi-weekly</option>
            <option value="month">Monthly</option>
            <option value="day">Daily</option>
          </select>
          {freqUnit === "bi-weekly" && (
            <div className="flex items-center gap-2">
              <Label className="text-sm">X =</Label>
              <Input
                type="number"
                min={1}
                value={freqCount}
                onChange={(e) => setFreqCount(parseInt(e.target.value || "1", 10))}
                className="w-20"
              />
            </div>
          )}
        </div>
        {cadenceError && (
          <p className="text-xs text-red-600">{cadenceError}</p>
        )}
      </div>

      {freqUnit !== "day" && (
        <div className="space-y-3">
          <Label className="text-base">Preferred {freqUnit === "week" ? "days" : "dates"}</Label>
          {freqUnit === "week" ? (
            <div className="grid grid-cols-4 gap-2">
              {[
                "Mon",
                "Tue",
                "Wed",
                "Thu",
                "Fri",
                "Sat",
                "Sun",
              ].map((d) => (
                <button
                  type="button"
                  key={d}
                  onClick={() => toggleWeekday(d)}
                  className={
                    "border rounded px-3 py-2 text-sm " +
                    (selectedWeekdays.includes(d)
                      ? "bg-primary text-white border-primary"
                      : "bg-card")
                  }
                >
                  {d}
                </button>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-10 gap-2">
              {Array.from({ length: 31 }, (_, i) => i + 1).map((n) => (
                <button
                  type="button"
                  key={n}
                  onClick={() => toggleDate(n)}
                  className={
                    "border rounded px-2 py-2 text-sm " +
                    (selectedDates.includes(n)
                      ? "bg-primary text-white border-primary"
                      : "bg-card")
                  }
                >
                  {n}
                </button>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2 mt-2">
            <input
              id="notSureSchedule"
              type="checkbox"
              checked={notSureSchedule}
              onChange={(e) => setNotSureSchedule(e.target.checked)}
            />
            <Label htmlFor="notSureSchedule" className="text-sm text-muted-foreground">
              I’m not sure yet
            </Label>
          </div>
        </div>
      )}
    </div>
  );
}
