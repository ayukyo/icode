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
if(DEFINED ICODE_WINDOWS_ARCH)
  add_executable(icode_windows_bootstrap icode_windows_bootstrap.c)
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
