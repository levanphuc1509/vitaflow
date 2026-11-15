# Đối chiếu thiết kế mobile (Stitch) ↔ mã nguồn

Cùng một route phục vụ cả PC lẫn mobile; `utils.render_template` tự chọn `templates/m/<tên>` khi là điện thoại.

| Thiết kế mobile (thư mục trong zip) | Template mobile | Route (giống PC) |
|---|---|---|
| `qu_n_l_01_t_ng_quan_i_u_h_nh_di_ng` | `m/manager/dashboard.html` | `/manager/` |
| `qu_n_l_02_nh_n_s_c_s_di_ng` | `m/manager/staff.html` | `/manager/staff` |
| `qu_n_l_03_h_s_body_ti_n_di_ng` | `m/manager/members.html` (+ popup `partials/member_card.html`) | `/manager/members` |
| `qu_n_l_04_ca_t_p_gi_m_s_t_di_ng` | `m/manager/shifts.html` | `/manager/shifts` |
| `qu_n_l_05_chat_dinh_d_ng_duy_t_qu_di_ng` | `m/manager/nutrition.html` + `m/manager/rewards.html` (tab “Chat & Quà”) | `/manager/nutrition`, `/manager/rewards` |
| `coach_01` … `coach_05` | `m/coach/dashboard · progress · checkin · nutrition · rewards` | `/coach/…` |
| `h_i_vi_n_01_b_ng_tin…` | `m/member/feed.html` | `/app/` |
| `h_i_vi_n_02_l_ch_ca…` | `m/member/schedule.html` | `/app/schedule` |
| `h_i_vi_n_03_dinh_d_ng_ai…` | `m/member/nutrition.html` | `/app/nutrition` |
| `h_i_vi_n_04_tr_m_qu_t_qr…` | `m/member/qr.html` | `/app/qr` |
| `h_i_vi_n_05_n_p_g_i_nhanh_vietqr` | `m/member/shop.html` + `order.html` | `/app/shop` |
| `h_i_vi_n_06_h_s_c_nh_n_body` | `m/member/profile.html` (trung tâm “Hồ Sơ & Nạp”) | `/app/profile` |
| `h_i_vi_n_07_b_ng_v_ng_v_qu` | `m/member/rewards.html` | `/app/rewards` |
| `h_i_vi_n_08_g_i_t_p_d_ch_v` | `m/member/membership.html` | `/app/membership` |
| `h_i_vi_n_09_tin_nh_n_chat_nh_m` | `m/member/messages.html` + `m/partials/chat.html` | `/app/messages` |
| `mobile_ng_nh_p_x_c_th_c…` | `m/auth/login.html`, `m/auth/register.html` | `/login`, `/register` |
| `mobile_trang_review…` | `m/public/landing.html` | `/` |

## Chuyển đổi giao diện
- Tự nhận diện theo User-Agent (điện thoại → mobile; iPad/tablet/PC → giao diện PC).
- Thủ công: `/view/mobile?next=…` hoặc `/view/desktop?next=…` (hoặc `?view=mobile|desktop` trên bất kỳ URL). Lựa chọn được nhớ trong phiên.
- Nút “Giao diện điện thoại” ở sidebar PC; “Xem giao diện máy tính” trong menu tài khoản mobile.

## Dùng chung giữa hai giao diện (bảo đảm chức năng giống nhau)
Toàn bộ route, API, phân quyền, CSRF; các file JS `static/js/{app,chat,feed,nutrition,profile,shop,checkin}.js`; các partial `menu_card`, `diet_side`, `member_card`.

## Chi tiết trong thiết kế KHÔNG có ở backend nên chưa làm (để tránh “bịa” chức năng)
Đăng nhập Google, đặt lịch InBody, “Thẩm định AI Vision” chấm ảnh tự động, tin nhắn thoại, bản tin “Thử thách tháng”, doanh thu/công suất theo tiền ở dashboard Quản lý, xuất báo cáo PDF.
