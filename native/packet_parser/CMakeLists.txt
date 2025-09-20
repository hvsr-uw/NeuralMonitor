cmake_minimum_required(VERSION 3.20)
project(neuralmonitor_packet_parser LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(packet_parser packet_parser.cpp)

