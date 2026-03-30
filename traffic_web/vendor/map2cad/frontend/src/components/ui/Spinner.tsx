interface SpinnerProps {
  size?: "sm" | "md" | "lg";
}

const sizes = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
  lg: "h-10 w-10 border-3",
};

export default function Spinner({ size = "md" }: SpinnerProps) {
  return (
    <div
      className={`animate-spin rounded-full border-blue-500 border-t-transparent ${sizes[size]}`}
      role="status"
      aria-label="Loading"
    />
  );
}
