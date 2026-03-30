import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
}

const variants = {
  primary: "bg-blue-600 text-white hover:bg-blue-700",
  secondary: "bg-gray-200 text-gray-800 hover:bg-gray-300",
  danger: "bg-red-600 text-white hover:bg-red-700",
};

export default function Button({ variant = "primary", className = "", disabled, ...props }: ButtonProps) {
  return (
    <button
      className={`rounded px-4 py-2 text-sm font-medium transition-colors ${
        disabled ? "cursor-not-allowed bg-gray-300 text-gray-500" : variants[variant]
      } ${className}`}
      disabled={disabled}
      {...props}
    />
  );
}
