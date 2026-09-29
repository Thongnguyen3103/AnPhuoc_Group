/**
 * SEGMENTS CONFIGURATION — AN PHƯỚC GROUP
 * Định nghĩa 5 phân khúc kinh doanh chính + Toàn bộ.
 * Bộ lọc nền (base) sẽ được áp dụng trước khi áp dụng bộ lọc tự do.
 */

const SEGMENTS = [
  {
    id: 'all',
    label: 'Toàn bộ',
    desc: 'Tất cả sản phẩm toàn hệ thống',
    base: {}
  },
  {
    id: 'core',
    label: 'Nhóm chủ đạo',
    subLabel: 'Chemise · Áo Thun · Quần Tây',
    default: true,
    desc: '3 nhóm sản phẩm cốt lõi (loại trừ Anamai & Bonjour)',
    base: {
      group_report: ['Chemise', 'Áo Thun', 'Quần Tây'],
      brand_exclude: ['Hiệu Anamai', 'Hiệu Bonjour']
    }
  },
  {
    id: 'golf',
    label: 'Golf',
    subLabel: 'Quần áo & Phụ kiện Golf',
    desc: 'Dòng sản phẩm chuyên biệt Golf',
    base: {
      product_group: ['Golf'],
      brand_exclude: ['Hiệu Anamai', 'Hiệu Bonjour']
    }
  },
  {
    id: 'leather',
    label: 'Phụ kiện da',
    subLabel: 'Dây nịt, Ví, Giày, Vali, Túi...',
    desc: 'Nhóm phụ kiện đồ da cao cấp',
    base: {
      product_group: ['Phụ Kiện Da'],
      brand_exclude: ['Hiệu Anamai', 'Hiệu Bonjour']
    }
  },
  {
    id: 'apparel_rest',
    label: 'Quần áo còn lại',
    subLabel: 'Áo khoác, Váy, Vest, Short, Kaki, Jean...',
    desc: 'Các nhóm trang phục thời trang khác ngoài nhóm chủ đạo & golf',
    base: {
      product_group: ['Áo', 'Quần', 'Váy', 'Vest Bộ', 'Fashion', 'Đồ Mặc Nhà', 'Bộ'],
      group_report_exclude: ['Chemise', 'Áo Thun', 'Quần Tây'],
      product_group_exclude: ['Golf', 'Phụ Kiện Da'],
      brand_exclude: ['Hiệu Anamai', 'Hiệu Bonjour']
    }
  },
  {
    id: 'anamai_bonjour',
    label: 'Anamai · Bonjour',
    subLabel: 'Nội y & Đồ lót nữ cao cấp',
    desc: 'Thương hiệu Anamai và Bonjour chuyên biệt',
    base: {
      brand: ['Hiệu Anamai', 'Hiệu Bonjour']
    }
  }
];

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { SEGMENTS };
}
