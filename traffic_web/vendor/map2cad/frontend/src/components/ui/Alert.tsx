interface AlertProps {
  type: "success" | "error" | "warning" | "info";
  children: React.ReactNode;
}

const styles = {
  success: "bg-green-50 border-green-200 text-green-800",
  error: "bg-red-50 border-red-200 text-red-800",
  warning: "bg-yellow-50 border-yellow-200 text-yellow-800",
  info: "bg-blue-50 border-blue-200 text-blue-800",
};

export default function Alert({ type, children }: AlertProps) {
  return (
    <div className={`rounded border px-4 py-3 text-sm ${styles[type]}`} role="alert">
      {children}
    </div>
  );
}
