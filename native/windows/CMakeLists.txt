cmake_minimum_required(VERSION 3.20)
project(icode_windows_helpers C)

if(NOT WIN32)
  message(FATAL_ERROR "The native Windows helpers are Windows-only")
endif()

# The production baseline begins with a non-executing bootstrap. Never expose
# setup/command entry points until provenance and isolation gates are satisfied.
if(CMAKE_GENERATOR_PLATFORM STREQUAL "ARM64")
  set(ICODE_WINDOWS_ARCH arm64)
elseif(CMAKE_GENERATOR_PLATFORM STREQUAL "x64")
  set(ICODE_WINDOWS_ARCH x64)
elseif(CMAKE_GENERATOR_PLATFORM STREQUAL "")
  string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" ICODE_WINDOWS_PROCESSOR)
  if(ICODE_WINDOWS_PROCESSOR MATCHES "^(arm64|aarch64)$")
    set(ICODE_WINDOWS_ARCH arm64)
  elseif(ICODE_WINDOWS_PROCESSOR MATCHES "^(amd64|x86_64)$")
    set(ICODE_WINDOWS_ARCH x64)
  endif()
endif()
option(ICODE_BUILD_WINDOWS_BOOTSTRAP "Build the verifier-bound bootstrap" ON)
set(ICODE_WINDOWS_PROVENANCE_VERIFIER "" CACHE FILEPATH "Actual architecture-matched Go verifier bytes")
if(ICODE_BUILD_WINDOWS_BOOTSTRAP)
  if(NOT DEFINED ICODE_WINDOWS_ARCH)
    message(FATAL_ERROR "Unsupported bootstrap architecture")
  endif()
  if(NOT IS_ABSOLUTE "${ICODE_WINDOWS_PROVENANCE_VERIFIER}" OR
     NOT EXISTS "${ICODE_WINDOWS_PROVENANCE_VERIFIER}")
    message(FATAL_ERROR "Bootstrap requires an explicit existing Go verifier")
  endif()
  find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
  set(ICODE_BINDING_HEADER "${CMAKE_CURRENT_BINARY_DIR}/icode_windows_verifier_binding.h")
  # A phony target runs on every build, including unchanged size/mtime inputs.
  # Nonzero generation blocks compilation and signing even with an old EXE.
  add_custom_target(icode_windows_bootstrap_binding
    COMMAND "${Python3_EXECUTABLE}" -B
      "${CMAKE_CURRENT_SOURCE_DIR}/../../scripts/windows_bootstrap_binding.py"
      --verifier "${ICODE_WINDOWS_PROVENANCE_VERIFIER}"
      --architecture "${ICODE_WINDOWS_ARCH}" --output "${ICODE_BINDING_HEADER}"
    BYPRODUCTS "${ICODE_BINDING_HEADER}"
    VERBATIM
  )
  add_executable(icode_windows_bootstrap icode_windows_bootstrap.c)
  add_dependencies(icode_windows_bootstrap icode_windows_bootstrap_binding)
  target_include_directories(icode_windows_bootstrap PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  set_property(SOURCE icode_windows_bootstrap.c APPEND PROPERTY
    OBJECT_DEPENDS "${ICODE_BINDING_HEADER}")
  set_target_properties(icode_windows_bootstrap PROPERTIES
    OUTPUT_NAME "icode-sandbox-windows-${ICODE_WINDOWS_ARCH}"
    C_STANDARD 11
    C_STANDARD_REQUIRED YES
    C_EXTENSIONS NO
  )
endif()

add_executable(icode_appcontainer_read_probe icode_appcontainer_read_probe.c)
set_target_properties(icode_appcontainer_read_probe PROPERTIES
  OUTPUT_NAME "icode-appcontainer-read-probe"
  C_STANDARD 11
  C_STANDARD_REQUIRED YES
  C_EXTENSIONS NO
)
target_compile_definitions(icode_appcontainer_read_probe PRIVATE
  UNICODE
  _UNICODE
  _WIN32_WINNT=0x0A00
)
target_link_libraries(icode_appcontainer_read_probe PRIVATE iphlpapi ws2_32)

add_executable(icode_wfp_event_probe icode_wfp_event_probe.c)
set_target_properties(icode_wfp_event_probe PROPERTIES
  OUTPUT_NAME "icode-wfp-event-probe"
  C_STANDARD 11
  C_STANDARD_REQUIRED YES
  C_EXTENSIONS NO
)
target_compile_definitions(icode_wfp_event_probe PRIVATE
  UNICODE
  _UNICODE
  _WIN32_WINNT=0x0A00
)
target_link_libraries(icode_wfp_event_probe PRIVATE advapi32 fwpuclnt userenv ws2_32)

if(MSVC)
  if(TARGET icode_windows_bootstrap)
    set_property(TARGET icode_windows_bootstrap PROPERTY
      MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
    )
    target_compile_options(icode_windows_bootstrap PRIVATE /W4 /WX)
  endif()
  set_property(TARGET icode_appcontainer_read_probe PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
  )
  set_property(TARGET icode_wfp_event_probe PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
  )
  target_compile_options(icode_appcontainer_read_probe PRIVATE /W4)
  target_compile_options(icode_wfp_event_probe PRIVATE /W4)
endif()
