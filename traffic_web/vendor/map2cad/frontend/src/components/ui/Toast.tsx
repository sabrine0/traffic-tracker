import type { Toast as ToastData } from "../../hooks/useToast";

const typeStyles: Record<ToastData["type"], string> = {
  success: "border-green-500 bg-green-50 text-green-800",
  error: "border-red-500 bg-red-50 text-red-800",
  warning: "border-amber-500 bg-amber-50 text-amber-800",
  info: "border-blue-500 bg-blue-50 text-blue-800",
};

const typeIcons: Record<ToastData["type"], string> = {
  success: "\u2713",
  error: "\u2717",
  warning: "\u26A0",
  info: "\u2139",
};

interface ToastContainerProps {
  toasts: ToastData[];
  onDismiss: (id: number) => void;
}

export default function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-14 right-4 z-50 flex flex-col gap-2" aria-live="polite">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="alert"
          onClick={() => onDismiss(toast.id)}
          className={`flex cursor-pointer items-center gap-2 rounded-lg border-l-4 px-4 py-3 shadow-md transition-all duration-300 ${typeStyles[toast.type]}`}
        >
          <span className="text-base">{typeIcons[toast.type]}</span>
          <span className="text-sm">{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
