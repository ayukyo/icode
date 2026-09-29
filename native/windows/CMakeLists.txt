cmake_minimum_required(VERSION 3.20)
project(icode_windows_diagnostic_probes C)

if(NOT WIN32)
  message(FATAL_ERROR "The AppContainer read-handle probe is Windows-only")
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
target_link_libraries(icode_appcontainer_read_probe PRIVATE ws2_32)

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
  set_property(TARGET icode_appcontainer_read_probe PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
  )
  set_property(TARGET icode_wfp_event_probe PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
  )
  target_compile_options(icode_appcontainer_read_probe PRIVATE /W4)
  target_compile_options(icode_wfp_event_probe PRIVATE /W4)
endif()
