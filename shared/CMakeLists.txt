cmake_minimum_required(VERSION 3.14)

add_library(shared_msgs INTERFACE)

get_filename_component(UWSYS_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

target_include_directories(shared_msgs INTERFACE
  "${UWSYS_REPO_ROOT}"
)

target_compile_features(shared_msgs INTERFACE cxx_std_17)
