import React from "react";

export function Separator({ className = "", ...props }) {
  return (
    <hr
      className={
        "border-t border-gray-200 my-4 w-full " + className
      }
      {...props}
    />
  );
}

export default Separator;
