# Bài viết ngắn — Lab 25 GPU FinOps

## 1. Baseline và optimized

NimbusAI có baseline **$27,133/tháng** và mức chi sau tối ưu **$14,627/tháng**. Tổng tiết kiệm là **$12,506/tháng (46.1%)**, đạt mục tiêu 40–95%. Riêng inference giảm từ **$6.488/1M-token** xuống **$1.129/1M-token**, tương đương **82.6%**.

## 2. Đóng góp của từng đòn bẩy

| Đòn bẩy | Tiết kiệm/tháng |
|---|---:|
| Inference (cascade/cache/batch) | $1,211 |
| Purchasing (spot/reserved) | $10,040 |
| Right-size util-lies | $655 |
| Kill idle GPUs | $600 |

Purchasing mang lại ROI tuyệt đối lớn nhất nên cần triển khai trước. Cascade/cache/batch có tỷ lệ giảm mạnh nhất trên unit economics của inference. Tắt GPU idle và right-size nhỏ hơn về giá trị tuyệt đối nhưng là quick win ít rủi ro.

## 3. GPU-Util lie

`gpu-h100-4` có GPU-Util **98.2%** nhưng MFU chỉ **19.4%**. GPU-Util chỉ nói clock có hoạt động; memory stall, I/O wait, kernel nhỏ hoặc launch overhead vẫn làm chỉ số này cao trong khi FLOPs hữu ích thấp. Vì vậy NimbusAI đang trả trọn giờ H100 nhưng chỉ nhận khoảng một phần năm năng lực tính toán. Right-size các GPU bị phát hiện giúp tiết kiệm **$655/tháng**; shutdown phần idle tiết kiệm thêm **$600/tháng**.

## 4. Hai phần mở rộng

### Cache economics

Với giả định một lần ghi cache có giá bằng một input uncached, điểm hòa vốn là **1.11 lượt đọc**. Dataset đạt **236.8 lượt** cho small tier và **61.2 lượt** cho large tier, nên cache có lợi ở cả hai. Policy mới chỉ bật cache khi số lượt đọc quan sát được vượt điểm hòa vốn, đồng thời cộng chi phí ghi cache vào optimized cost.

### Reasoning budget

Reasoning chiếm **8.4% traffic**, nhưng chiếm **16.4% optimized cost** và **94.0% năng lượng** vì output dài hơn và hệ số năng lượng 80×. Đề xuất chỉ route sang reasoning khi confidence thấp hoặc task complexity vượt ngưỡng, đồng thời cap ở **5% traffic**. Mô phỏng cho thấy cap này tiết kiệm **$12.30/tháng** và **358.0 kWh/tháng**.

## 5. Khuyến nghị ưu tiên

1. Áp dụng spot có checkpoint cho job interruptible và reserved cho inference ổn định; đây là lever lớn nhất.
2. Giữ cascade/cache/batch nhưng theo dõi `$/1M-token`; cache phải qua break-even gate và reasoning phải qua routing budget.
3. Thiết lập auto-shutdown cho idle GPU, alert theo MFU/MBU thay vì GPU-Util, và duy trì tag coverage trên 80% trước khi chargeback.

Về bền vững, một query đại diện dùng **0.24 Wh**. Chuyển từ `us-east-1` sang `europe-north1` giảm khoảng **92.1% carbon** và **25.0% chi phí điện** theo snapshot tháng 6/2026; cần cân bằng thêm latency trước khi triển khai thực tế.
