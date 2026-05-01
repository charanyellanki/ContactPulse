import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Landing } from "@/views/Landing";
import { CustomerExperience } from "@/views/CustomerExperience";
import { OperatorConsole } from "@/views/OperatorConsole";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/cx" element={<CustomerExperience />} />
        <Route path="/operator" element={<OperatorConsole />} />
        <Route path="/operator/:tab" element={<OperatorConsole />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
