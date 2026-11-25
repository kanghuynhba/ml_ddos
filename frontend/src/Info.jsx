// Explanations for the "i" icons, keyed by metric
export const GLOSSARY = {
  f1: "F1-score: trung bình điều hòa của Precision (tỉ lệ cảnh báo đúng) và Recall (tỉ lệ tấn công bị bắt được), từ 0 đến 1, càng cao càng tốt. Dùng F1 thay vì Accuracy vì dữ liệu mất cân bằng giữa lưu lượng tấn công và bình thường.",
  globalF1: "F1 của mô hình toàn cục (sau khi server tổng hợp bằng FedAvg) trên tập kiểm thử chung: gồm phần test của mọi client và thêm tấn công SYN/UDP của ngày khác (cross-day). Đo khả năng phát hiện mọi loại tấn công, kể cả loại mà một client chưa từng gặp.",
  bestLocal: "F1 cao nhất trên tập kiểm thử chung trong các mô hình chỉ huấn luyện cục bộ: mỗi client tự train trên dữ liệu của mình, không liên kết. Đây là mốc so sánh (baseline) cho FedAvg.",
  gain: "Hiệu số = F1 của FedAvg − F1 của mô hình cục bộ tốt nhất, cùng trên tập kiểm thử chung. Dương (xanh): mô hình liên kết tốt hơn. Âm (đỏ): vẫn có client tự train tốt hơn.",
  round: "Một vòng (round): server gửi mô hình toàn cục xuống → mỗi client train cục bộ E epoch → client gửi trọng số lên → server lấy trung bình có trọng số theo số mẫu. Vòng 0 là mô hình khởi tạo, chưa huấn luyện.",
  loss: "Loss = binary cross-entropy trên tập kiểm thử chung: đo độ lệch giữa xác suất dự đoán và nhãn thật, càng thấp càng tốt. Loss tăng trong khi F1 đứng yên thường do mô hình quá tự tin hoặc các client trôi xa nhau vì dữ liệu non-IID.",
  compare: "Hàng = mô hình, cột = tập kiểm thử, giá trị = F1. Mô hình cục bộ thường chỉ tốt trên loại tấn công nó đã thấy; mô hình FedAvg được kỳ vọng tốt ở mọi cột.",
  ownTest: "F1 trên phần test riêng của client đó (cùng loại tấn công với dữ liệu train của nó).",
  globalTest: "Tập kiểm thử chung: phần test của mọi client cộng thêm tấn công SYN/UDP của ngày khác (cross-day) và lưu lượng bình thường.",
  fedavg: "FedAvg: server tính trọng số mới w = Σ (n_k / N) · w_k, với n_k là số mẫu train của client k và N là tổng số mẫu. Client có nhiều dữ liệu hơn có ảnh hưởng lớn hơn.",
  fedprox: "FedProx: giống FedAvg nhưng mỗi client thêm số hạng phạt μ/2·‖w − w_toàn_cục‖² vào loss khi train cục bộ. Số hạng này giữ client không trôi quá xa mô hình toàn cục, giúp ổn định khi dữ liệu non-IID nặng.",
  bytes: "Dung lượng trọng số mô hình trao đổi trong vòng: ↓ server gửi xuống client, ↑ client gửi lên server. Chỉ có trọng số, không có dữ liệu lưu lượng thô.",
  valF1: "F1 trên tập validation riêng của từng client, đo ngay sau khi client nhận mô hình toàn cục của vòng đó.",
  trainLoss: "Loss trung bình khi client huấn luyện cục bộ trong vòng đó.",
  samples: "Số mẫu (flow) dùng để train tại client. Tỉ lệ giữa 3 client là 1:4:16, mô phỏng dữ liệu không cân bằng.",
  nonIID: "Mỗi client gặp một loại tấn công khác nhau (SYN, DNS, UDP) và có lượng dữ liệu khác nhau → dữ liệu non-IID, giống thực tế nhiều node Suricata ở các tổ chức khác nhau.",
};

// Circled "i" that shows an explanation on hover or keyboard focus
export function Info({ k, text }) {
  const t = text ?? GLOSSARY[k];
  return (
    <span className="info" tabIndex={0} role="button" aria-label={`Giải thích: ${t}`} onClick={(e) => e.stopPropagation()}>
      i<span className="info-tip" role="tooltip">{t}</span>
    </span>
  );
}
