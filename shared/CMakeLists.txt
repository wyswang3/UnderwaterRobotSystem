cmake_minimum_required(VERSION 3.16)

# Header-only shared module: message & protocol definitions
add_library(shared_msgs INTERFACE)

# 约定：使用方通过 #include "shared/..." 引用
# 因此 include 目录应当指向 repo root（shared 的上一级）
get_filename_component(UWSYS_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

target_include_directories(shared_msgs INTERFACE
  "${UWSYS_REPO_ROOT}"
)

# 统一 C++ 标准（不要在这里塞过多 warning/优化选项，避免影响各子项目）
target_compile_features(shared_msgs INTERFACE cxx_std_17)
