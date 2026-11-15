"""calculator.py - Tính BMR, TDEE và chia tỷ lệ Macro (Protein / Carb / Fat).

Công thức BMR: Mifflin-St Jeor (độ chính xác tốt cho người trưởng thành).
Năng lượng: 1g Protein = 4 kcal, 1g Carb = 4 kcal, 1g Fat = 9 kcal.
"""

# Hệ số vận động (PAL - Physical Activity Level)
HE_SO_VAN_DONG = {
    "it": 1.2,          # Ít vận động (ngồi nhiều, ít tập)
    "nhe": 1.375,       # Tập nhẹ 1-3 buổi/tuần
    "vua": 1.55,        # Tập vừa 3-5 buổi/tuần
    "nhieu": 1.725,     # Tập nặng 6-7 buổi/tuần
    "rat_nhieu": 1.9,   # Vận động viên / lao động nặng
}

# Điều chỉnh calo theo mục tiêu (nhân với TDEE)
MUC_TIEU = {
    # Khóa dùng trên form AI Coach / hồ sơ
    "giam_can": 0.80,   # Giảm ~20%
    "can_bang": 1.00,   # Duy trì
    "tang_co": 1.10,    # Tăng ~10%
    # Khóa cũ - giữ để tương thích ngược
    "giu_can": 1.00,
    "tang_can": 1.10,
}

# Tỷ lệ macro (% Protein, % Carb, % Fat) - tổng phải bằng 100
TI_LE_MACRO = {
    "can_bang": (20, 50, 30),
    "giam_can": (30, 40, 30),
    "tang_co": (30, 45, 25),
    "low_carb": (30, 25, 45),
}

KCAL_PER_GAM = {"protein": 4, "carb": 4, "fat": 9}


def _kiem_tra_dau_vao(tuoi, gioi_tinh, can_nang, chieu_cao):
    if gioi_tinh not in ("nam", "nu"):
        raise ValueError("gioi_tinh phải là 'nam' hoặc 'nu'")
    if not (18 <= tuoi <= 100):
        raise ValueError("tuoi phải nằm trong khoảng 18-100 (công thức dành cho người trưởng thành)")
    if not (20 <= can_nang <= 300):
        raise ValueError("can_nang (kg) phải nằm trong khoảng 20-300")
    if not (100 <= chieu_cao <= 250):
        raise ValueError("chieu_cao (cm) phải nằm trong khoảng 100-250")


def tinh_bmr(tuoi, gioi_tinh, can_nang, chieu_cao):
    """BMR (kcal/ngày) theo Mifflin-St Jeor.

    Nam: 10*kg + 6.25*cm - 5*tuoi + 5
    Nữ : 10*kg + 6.25*cm - 5*tuoi - 161
    """
    _kiem_tra_dau_vao(tuoi, gioi_tinh, can_nang, chieu_cao)
    bmr = 10 * can_nang + 6.25 * chieu_cao - 5 * tuoi
    bmr += 5 if gioi_tinh == "nam" else -161
    return round(bmr, 1)


def tinh_tdee(bmr, he_so_van_dong):
    """TDEE = BMR x hệ số vận động. Nhận khóa (vd 'vua') hoặc số (vd 1.55)."""
    if isinstance(he_so_van_dong, str):
        if he_so_van_dong not in HE_SO_VAN_DONG:
            raise ValueError(f"Hệ số không hợp lệ. Chọn: {list(HE_SO_VAN_DONG)}")
        he_so_van_dong = HE_SO_VAN_DONG[he_so_van_dong]
    if not (1.0 <= he_so_van_dong <= 2.5):
        raise ValueError("he_so_van_dong phải nằm trong khoảng 1.0-2.5")
    return round(bmr * he_so_van_dong, 1)


def tinh_calo_muc_tieu(tdee, muc_tieu="giu_can"):
    """Điều chỉnh TDEE theo mục tiêu: giam_can / giu_can / tang_can."""
    if muc_tieu not in MUC_TIEU:
        raise ValueError(f"Mục tiêu không hợp lệ. Chọn: {list(MUC_TIEU)}")
    return round(tdee * MUC_TIEU[muc_tieu], 1)


def chia_macro(calo, ti_le="can_bang"):
    """Chia calo thành gam Protein/Carb/Fat.

    ti_le: tên preset trong TI_LE_MACRO hoặc tuple (%P, %C, %F) cộng lại = 100.
    """
    if isinstance(ti_le, str):
        if ti_le not in TI_LE_MACRO:
            raise ValueError(f"Tỷ lệ không hợp lệ. Chọn: {list(TI_LE_MACRO)}")
        ti_le = TI_LE_MACRO[ti_le]
    p_pct, c_pct, f_pct = ti_le
    if round(p_pct + c_pct + f_pct) != 100:
        raise ValueError("Tổng tỷ lệ Protein + Carb + Fat phải bằng 100%")

    return {
        "protein_g": round(calo * p_pct / 100 / KCAL_PER_GAM["protein"]),
        "carb_g": round(calo * c_pct / 100 / KCAL_PER_GAM["carb"]),
        "fat_g": round(calo * f_pct / 100 / KCAL_PER_GAM["fat"]),
    }


def tinh_tat_ca(tuoi, gioi_tinh, can_nang, chieu_cao, he_so_van_dong,
                muc_tieu="giu_can", ti_le="can_bang"):
    """Chạy toàn bộ quy trình, trả về dict kết quả."""
    bmr = tinh_bmr(tuoi, gioi_tinh, can_nang, chieu_cao)
    tdee = tinh_tdee(bmr, he_so_van_dong)
    calo = tinh_calo_muc_tieu(tdee, muc_tieu)
    return {
        "bmr": bmr,
        "tdee": tdee,
        "calo_muc_tieu": calo,
        "macro": chia_macro(calo, ti_le),
    }


if __name__ == "__main__":
    # Ví dụ: nam, 25 tuổi, 70kg, 175cm, tập vừa, muốn giảm cân
    kq = tinh_tat_ca(25, "nam", 70, 175, "vua",
                     muc_tieu="giam_can", ti_le="giam_can")
    print(f"BMR           : {kq['bmr']} kcal")
    print(f"TDEE          : {kq['tdee']} kcal")
    print(f"Calo mục tiêu : {kq['calo_muc_tieu']} kcal")
    m = kq["macro"]
    print(f"Macro         : Protein {m['protein_g']}g | "
          f"Carb {m['carb_g']}g | Fat {m['fat_g']}g")
